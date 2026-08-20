import json


class TrainingService:
    def __init__(self, coordinator):
        self.coordinator = coordinator

    def submit_session(self, user_id: int, data: dict):
        return self.coordinator.submit_session(
            user_id,
            data["exercise_name"],
            data["score"],
            data["duration"],
        )

    def save_pose_record(self, user_id: int, data: dict):
        payload = dict(data, user_id=user_id)
        landmarks = payload.pop("landmarks", None)
        raw_score = payload.pop("raw_score", None)
        if landmarks is not None:
            try:
                raw_payload = json.loads(payload.get("raw_landmarks_json") or "{}")
                if not isinstance(raw_payload, dict):
                    raw_payload = {}
            except (TypeError, json.JSONDecodeError):
                raw_payload = {}
            raw_payload["landmarks"] = landmarks
            raw_payload.setdefault("source", "mediapipe" if landmarks else "keyboard")
            payload["raw_landmarks_json"] = json.dumps(raw_payload, ensure_ascii=False)

        evaluation = self.coordinator.motion.evaluate_structured(
            payload.get("exercise_name", "未知动作"),
            raw_score if raw_score is not None else payload.get("stability_score", 0),
            payload,
        )
        features = evaluation.get("motion_features") or {}
        angles = features.get("angle") or {}
        payload["confidence"] = features.get("confidence") or payload.get("confidence", 0)
        payload["stability_score"] = features.get("stability_score") or payload.get("stability_score", 0)
        payload["knee_angle"] = angles.get("knee")
        payload["hip_angle"] = angles.get("hip")
        payload["shoulder_balance"] = angles.get("shoulder_balance")
        record_id = self.coordinator.save_pose_record(payload)
        return {
            "id": record_id,
            "message": "姿态识别记录已保存并完成动作评估",
            "evaluation": evaluation.get("evaluation") or {},
            "motion_features": features,
            "mode": evaluation.get("mode", "fallback"),
            "fallback_reason": evaluation.get("fallback_reason"),
        }
