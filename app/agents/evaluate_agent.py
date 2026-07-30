from __future__ import annotations

from typing import Any

from app.agents.base import BaseAgent
from app.agents.mediapipe_adapter import MediaPipeAdapter
from app.agents.schemas import EvaluateOutput


class EvaluateAgent(BaseAgent):
    prompt_module = "app.agents.prompts.evaluate_prompt"
    output_schema = EvaluateOutput

    def __init__(self, *args: Any, pose_adapter: MediaPipeAdapter | None = None, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.pose_adapter = pose_adapter or MediaPipeAdapter()

    def evaluate(
        self,
        exercise_name: str,
        raw_score: int | float,
        pose_data: dict[str, Any] | str | None = None,
    ) -> dict[str, Any]:
        score = self._score(raw_score)
        features = self.pose_adapter.to_features(pose_data, fallback_score=score)
        payload = {
            "exercise_name": exercise_name,
            "raw_score": score,
            "motion_features": features,
        }
        try:
            result = self.run(payload)
            evaluation = self._sanitize(result["evaluation"], features, score)
            return {
                "evaluation": evaluation,
                "motion_features": features,
                **self.online_metadata(),
            }
        except self.recoverable_errors as exc:
            return self._fallback_result(score, features, self._safe_reason(exc))

    async def aevaluate(
        self,
        exercise_name: str,
        raw_score: int | float,
        pose_data: dict[str, Any] | str | None = None,
    ) -> dict[str, Any]:
        score = self._score(raw_score)
        features = self.pose_adapter.to_features(pose_data, fallback_score=score)
        payload = {
            "exercise_name": exercise_name,
            "raw_score": score,
            "motion_features": features,
        }
        try:
            result = await self.arun(payload)
            evaluation = self._sanitize(result["evaluation"], features, score)
            return {
                "evaluation": evaluation,
                "motion_features": features,
                **self.online_metadata(),
            }
        except self.recoverable_errors as exc:
            return self._fallback_result(score, features, self._safe_reason(exc))

    def pose_features(
        self,
        pose_data: dict[str, Any] | str | None,
        fallback_score: int | float = 0,
    ) -> dict[str, Any]:
        return self.pose_adapter.to_features(pose_data, fallback_score=fallback_score)

    def _sanitize(
        self,
        evaluation: dict[str, Any],
        features: dict[str, Any],
        default_score: int,
    ) -> dict[str, Any]:
        available = set(features["available_features"]) & {
            "knee",
            "hip",
            "shoulder_balance",
            "stability_score",
        }
        blocked_terms = []
        if "knee" not in available:
            blocked_terms.extend(("膝", "knee"))
        if "hip" not in available:
            blocked_terms.extend(("髋", "hip"))
        if "shoulder_balance" not in available:
            blocked_terms.extend(("肩", "shoulder"))
        mistakes = [
            text
            for text in evaluation.get("mistakes", [])
            if not any(term.lower() in text.lower() for term in blocked_terms)
        ]
        suggestions = [
            text
            for text in evaluation.get("suggestions", [])
            if not any(term.lower() in text.lower() for term in blocked_terms)
        ]
        if not available:
            mistakes = []
            suggestions = ["补充完整且可见的 MediaPipe 关键点后再进行姿态纠错。"]
            risk_level = "unknown"
        else:
            risk_level = evaluation.get("risk_level", "unknown")
        return EvaluateOutput.model_validate(
            {
                "evaluation": {
                    "score": evaluation.get("score", default_score),
                    "mistakes": mistakes,
                    "suggestions": suggestions,
                    "risk_level": risk_level,
                }
            }
        ).evaluation.model_dump()

    def _fallback_result(
        self,
        score: int,
        features: dict[str, Any],
        reason: str,
    ) -> dict[str, Any]:
        available = set(features["available_features"]) & {
            "knee",
            "hip",
            "shoulder_balance",
            "stability_score",
        }
        mistakes = []
        suggestions = []
        stability_score = features.get("stability_score")
        shoulder_balance = features["angle"].get("shoulder_balance")
        if stability_score is not None and stability_score < 65:
            mistakes.append("输入的稳定度评分偏低。")
            suggestions.append("降低动作速度，并在稳定后再增加幅度。")
        if shoulder_balance is not None and shoulder_balance > 8:
            mistakes.append("关键点显示左右肩高度差较大。")
            suggestions.append("正对镜头重新校准站位，并保持双肩水平。")
        if not available:
            suggestions.append("补充完整且可见的 MediaPipe 关键点后再进行姿态纠错。")
            risk_level = "unknown"
        elif score < 60:
            risk_level = "medium"
        else:
            risk_level = "low"
        evaluation = EvaluateOutput.model_validate(
            {
                "evaluation": {
                    "score": score,
                    "mistakes": mistakes,
                    "suggestions": suggestions,
                    "risk_level": risk_level,
                }
            }
        ).evaluation.model_dump()
        return {
            "evaluation": evaluation,
            "motion_features": features,
            **self.fallback_metadata(reason=reason),
        }

    def _score(self, value: int | float) -> int:
        try:
            return int(round(max(0, min(100, float(value)))))
        except (TypeError, ValueError):
            return 0


MotionAgent = EvaluateAgent
