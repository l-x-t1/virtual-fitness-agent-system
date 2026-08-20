from __future__ import annotations

from typing import Any

from app.agents.evaluate_agent import EvaluateAgent
from app.llm.client import ToolSpec
from app.tools.registry import tool_result


class PoseEvaluationTool:
    def __init__(self, agent: EvaluateAgent | None = None):
        self.agent = agent or EvaluateAgent()

    def evaluate_pose(
        self,
        exercise_name: str,
        landmarks: list[dict[str, Any]] | None = None,
        raw_score: float | None = None,
        confidence: float | None = None,
        stability_score: float | None = None,
    ) -> dict[str, Any]:
        """将真实 MediaPipe 关键点转换为动作特征并生成安全纠错结果。"""
        pose_data = {
            "landmarks": list(landmarks or []),
            "confidence": confidence,
            "stability_score": stability_score,
        }
        result = self.agent.evaluate(
            str(exercise_name or "未知动作")[:100],
            raw_score if raw_score is not None else stability_score or 0,
            pose_data,
        )
        has_landmarks = bool(landmarks)
        return tool_result(
            ok=True,
            mode=str(result.get("mode") or "fallback"),
            source="mediapipe-evaluate-agent",
            data={
                "exercise_name": str(exercise_name or "未知动作")[:100],
                "evaluation": result.get("evaluation") or {},
                "motion_features": result.get("motion_features") or {},
            },
            fallback_reason=(
                "missing_landmarks"
                if not has_landmarks
                else result.get("fallback_reason")
            ),
        )

    def spec(self) -> ToolSpec:
        point = {
            "type": "object",
            "properties": {
                "x": {"type": "number"},
                "y": {"type": "number"},
                "z": {"type": "number"},
                "visibility": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": ["x", "y"],
            "additionalProperties": True,
        }
        return ToolSpec(
            name="evaluate_pose",
            description="根据 MediaPipe landmarks 评估动作，返回评分、错误、建议、风险和运动特征。",
            handler=self.evaluate_pose,
            parameters={
                "type": "object",
                "properties": {
                    "exercise_name": {"type": "string"},
                    "landmarks": {"type": "array", "items": point},
                    "raw_score": {"type": ["number", "null"], "minimum": 0, "maximum": 100},
                    "confidence": {"type": ["number", "null"], "minimum": 0, "maximum": 100},
                    "stability_score": {"type": ["number", "null"], "minimum": 0, "maximum": 100},
                },
                "required": ["exercise_name", "landmarks"],
                "additionalProperties": False,
            },
        )
