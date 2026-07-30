from __future__ import annotations

import json
import math
from typing import Any


class MediaPipeAdapter:
    """Convert MediaPipe pose payloads into compact motion features for LLM evaluation."""

    LEFT_SHOULDER = 11
    RIGHT_SHOULDER = 12
    LEFT_HIP = 23
    RIGHT_HIP = 24
    LEFT_KNEE = 25
    RIGHT_KNEE = 26
    LEFT_ANKLE = 27
    RIGHT_ANKLE = 28

    def to_features(self, pose_data: dict[str, Any] | str | None, fallback_score: int | float = 0) -> dict[str, Any]:
        payload = self._payload(pose_data)
        landmarks = self._landmarks(payload)

        knee_angle = self._number(payload.get("knee_angle"))
        hip_angle = self._number(payload.get("hip_angle"))
        shoulder_balance = self._number(payload.get("shoulder_balance"))
        left_knee_angle = None
        right_knee_angle = None
        left_hip_angle = None
        right_hip_angle = None

        if landmarks:
            left_knee_angle = self._angle(landmarks, self.LEFT_HIP, self.LEFT_KNEE, self.LEFT_ANKLE)
            right_knee_angle = self._angle(landmarks, self.RIGHT_HIP, self.RIGHT_KNEE, self.RIGHT_ANKLE)
            left_hip_angle = self._angle(landmarks, self.LEFT_SHOULDER, self.LEFT_HIP, self.LEFT_KNEE)
            right_hip_angle = self._angle(landmarks, self.RIGHT_SHOULDER, self.RIGHT_HIP, self.RIGHT_KNEE)
            if knee_angle is None:
                knee_angle = self._average([left_knee_angle, right_knee_angle])
            if hip_angle is None:
                hip_angle = self._average([left_hip_angle, right_hip_angle])
            if shoulder_balance is None:
                shoulder_balance = self._balance(
                    self._point(landmarks, self.LEFT_SHOULDER),
                    self._point(landmarks, self.RIGHT_SHOULDER),
                )

        confidence = self._number(payload.get("confidence"))
        stability_score = self._number(payload.get("stability_score"))
        posture_score = self._posture_score(confidence, stability_score, knee_angle, hip_angle, shoulder_balance, fallback_score)

        angles = {
            "knee": self._rounded(knee_angle),
            "hip": self._rounded(hip_angle),
            "shoulder_balance": self._rounded(shoulder_balance),
            "left_knee": self._rounded(left_knee_angle),
            "right_knee": self._rounded(right_knee_angle),
            "left_hip": self._rounded(left_hip_angle),
            "right_hip": self._rounded(right_hip_angle),
        }
        available = [name for name, value in angles.items() if value is not None]
        if stability_score is not None:
            available.append("stability_score")
        if confidence is not None:
            available.append("confidence")
        expected = ["knee", "hip", "shoulder_balance", "stability_score"]

        return {
            "angle": angles,
            "stability": self._stability_label(stability_score, shoulder_balance),
            "stability_score": self._rounded(stability_score),
            "confidence": self._rounded(confidence),
            "range": self._range_label(knee_angle, hip_angle),
            "posture_score": posture_score,
            "available_features": available,
            "missing_features": [name for name in expected if name not in available],
            "landmark_count": len(landmarks),
        }

    def _payload(self, pose_data: dict[str, Any] | str | None) -> dict[str, Any]:
        if pose_data is None:
            return {}
        if isinstance(pose_data, dict):
            payload = dict(pose_data)
        else:
            try:
                payload = json.loads(pose_data or "{}")
            except json.JSONDecodeError:
                return {"raw_landmarks_json": pose_data}
        raw = payload.get("raw_landmarks_json")
        if isinstance(raw, str) and raw.strip():
            try:
                raw_payload = json.loads(raw)
                if isinstance(raw_payload, dict):
                    payload = {**raw_payload, **payload}
                elif isinstance(raw_payload, list):
                    payload.setdefault("landmarks", raw_payload)
            except json.JSONDecodeError:
                pass
        return payload

    def _landmarks(self, payload: dict[str, Any]) -> list[Any]:
        for key in ("landmarks", "pose_landmarks", "poseLandmarks"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
        return []

    def _angle(self, landmarks: list[Any], a_index: int, b_index: int, c_index: int) -> float | None:
        a = self._point(landmarks, a_index)
        b = self._point(landmarks, b_index)
        c = self._point(landmarks, c_index)
        if not a or not b or not c:
            return None
        ba = (a["x"] - b["x"], a["y"] - b["y"])
        bc = (c["x"] - b["x"], c["y"] - b["y"])
        denominator = math.hypot(*ba) * math.hypot(*bc)
        if not denominator:
            return None
        cosine = max(-1.0, min(1.0, (ba[0] * bc[0] + ba[1] * bc[1]) / denominator))
        return math.degrees(math.acos(cosine))

    def _point(self, landmarks: list[Any], index: int) -> dict[str, float] | None:
        if index >= len(landmarks):
            return None
        point = landmarks[index]
        if isinstance(point, dict):
            x = self._number(point.get("x"))
            y = self._number(point.get("y"))
            visibility = self._number(point.get("visibility"))
        else:
            x = self._number(getattr(point, "x", None))
            y = self._number(getattr(point, "y", None))
            visibility = self._number(getattr(point, "visibility", None))
        if x is None or y is None or (visibility is not None and visibility < 0.5):
            return None
        return {"x": x, "y": y}

    def _balance(self, left: dict[str, float] | None, right: dict[str, float] | None) -> float | None:
        if not left or not right:
            return None
        return abs(left["y"] - right["y"]) * 100

    def _posture_score(self, confidence, stability_score, knee_angle, hip_angle, shoulder_balance, fallback_score) -> int:
        components = []
        for value in (confidence, stability_score):
            if value is not None:
                components.append(max(0, min(100, float(value))))
        if knee_angle is not None:
            components.append(max(0, 100 - abs(100 - knee_angle) * 0.8))
        if hip_angle is not None:
            components.append(max(0, 100 - abs(150 - hip_angle) * 0.5))
        if shoulder_balance is not None:
            components.append(max(0, 100 - shoulder_balance * 3))
        if not components:
            components.append(float(fallback_score or 0))
        return int(round(sum(components) / len(components)))

    def _stability_label(self, stability_score, shoulder_balance) -> str:
        if stability_score is not None:
            if stability_score >= 85:
                return "stable"
            if stability_score >= 65:
                return "moderate"
            return "unstable"
        if shoulder_balance is not None:
            if shoulder_balance <= 3:
                return "stable"
            if shoulder_balance <= 8:
                return "moderate"
            return "unstable"
        return "unknown"

    def _range_label(self, knee_angle, hip_angle) -> str:
        if knee_angle is None and hip_angle is None:
            return "unknown"
        if knee_angle is not None and knee_angle < 70:
            return "deep"
        if knee_angle is not None and knee_angle > 155:
            return "limited"
        if hip_angle is not None and hip_angle < 90:
            return "compressed"
        return "normal"

    def _average(self, values: list[float | None]) -> float | None:
        valid = [value for value in values if value is not None]
        if not valid:
            return None
        return sum(valid) / len(valid)

    def _number(self, value: Any) -> float | None:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _rounded(self, value: float | None) -> float | None:
        return round(value, 1) if value is not None else None
