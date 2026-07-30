from __future__ import annotations

from typing import Any

from app.agents.base import BaseAgent
from app.agents.schemas import ProfileOutput


class ProfileAgent(BaseAgent):
    prompt_module = "app.agents.prompts.profile_prompt"
    output_schema = ProfileOutput

    def summarize(
        self,
        user: dict[str, Any],
        history: list[dict[str, Any]] | None = None,
        behavior: list[Any] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "user_info": dict(user or {}),
            "history": list(history or []),
            "behavior": list(behavior or []),
        }
        try:
            result = self.run(payload)
            return {**result, **self.online_metadata()}
        except self.recoverable_errors as exc:
            return {
                "profile": self._fallback_profile(payload),
                **self.fallback_metadata(exc),
            }

    async def asummarize(
        self,
        user: dict[str, Any],
        history: list[dict[str, Any]] | None = None,
        behavior: list[Any] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "user_info": dict(user or {}),
            "history": list(history or []),
            "behavior": list(behavior or []),
        }
        try:
            result = await self.arun(payload)
            return {**result, **self.online_metadata()}
        except self.recoverable_errors as exc:
            return {
                "profile": self._fallback_profile(payload),
                **self.fallback_metadata(exc),
            }

    def _fallback_profile(self, payload: dict[str, Any]) -> dict[str, Any]:
        user = payload["user_info"]
        history = payload["history"]
        behavior = payload["behavior"]
        fitness_level = str(user.get("fitness_level") or "信息不足")
        goals = self._strings(user.get("goals") or user.get("goal"))
        preferences = self._strings(user.get("preferences") or user.get("preference"))
        injury = user.get("injuries") or user.get("injury_history")
        risk_flags = []
        if injury:
            risk_flags.append(f"输入记录的伤病/不适信息：{injury}")
        habits = self._strings(user.get("habits"))
        habits.extend(self._strings(behavior))
        if history:
            habits.append(f"已提供 {len(history)} 条训练记录")

        pieces = [f"体能水平：{fitness_level}"]
        if goals:
            pieces.append("目标：" + "、".join(goals))
        if preferences:
            pieces.append("偏好：" + "、".join(preferences))
        if risk_flags:
            pieces.append("需关注已输入的伤病或不适信息")
        if not goals and not preferences and not risk_flags:
            pieces.append("当前输入不足以形成更具体画像")
        return ProfileOutput.model_validate(
            {
                "profile": {
                    "fitness_level": fitness_level,
                    "goals": goals,
                    "preferences": preferences,
                    "risk_flags": risk_flags,
                    "habits": list(dict.fromkeys(habits)),
                    "summary": "；".join(pieces) + "。",
                }
            }
        ).profile.model_dump()

    def _strings(self, value: Any) -> list[str]:
        if value in (None, ""):
            return []
        if isinstance(value, (list, tuple, set)):
            return [str(item).strip() for item in value if str(item).strip()]
        return [part.strip() for part in str(value).replace("，", ",").split(",") if part.strip()]
