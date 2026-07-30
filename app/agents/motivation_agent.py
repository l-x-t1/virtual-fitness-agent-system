from __future__ import annotations

from typing import Any

from app.agents.base import BaseAgent
from app.agents.schemas import MotivationOutput


class MotivationAgent(BaseAgent):
    prompt_module = "app.agents.prompts.motivation_prompt"
    output_schema = MotivationOutput

    def settle(
        self,
        user: dict[str, Any],
        score: int | float,
        duration: int | float,
        *,
        points: int | float = 0,
        total_points: int | float = 0,
        level: int = 1,
        history: list[dict[str, Any]] | None = None,
        unlocked_levels: list[str] | None = None,
    ) -> dict[str, Any]:
        payload = self._payload(
            user, score, duration, points, total_points, level, history, unlocked_levels
        )
        try:
            result = self.run(payload)
            return {**result, **self.online_metadata()}
        except self.recoverable_errors as exc:
            return {**self._fallback(payload), **self.fallback_metadata(exc)}

    async def asettle(
        self,
        user: dict[str, Any],
        score: int | float,
        duration: int | float,
        *,
        points: int | float = 0,
        total_points: int | float = 0,
        level: int = 1,
        history: list[dict[str, Any]] | None = None,
        unlocked_levels: list[str] | None = None,
    ) -> dict[str, Any]:
        payload = self._payload(
            user, score, duration, points, total_points, level, history, unlocked_levels
        )
        try:
            result = await self.arun(payload)
            return {**result, **self.online_metadata()}
        except self.recoverable_errors as exc:
            return {**self._fallback(payload), **self.fallback_metadata(exc)}

    def _payload(
        self,
        user: dict[str, Any],
        score: int | float,
        duration: int | float,
        points: int | float,
        total_points: int | float,
        level: int,
        history: list[dict[str, Any]] | None,
        unlocked_levels: list[str] | None,
    ) -> dict[str, Any]:
        return {
            "nickname": user.get("nickname") or "用户",
            "score": self._number(score),
            "duration": self._number(duration),
            "points": self._number(points),
            "total_points": self._number(total_points),
            "level": int(level or 1),
            "history": list(history or []),
            "unlocked_levels": list(unlocked_levels or []),
        }

    def _fallback(self, payload: dict[str, Any]) -> dict[str, Any]:
        nickname = payload["nickname"]
        score = payload["score"]
        duration = payload["duration"]
        unlocked = payload["unlocked_levels"]
        if score >= 90:
            detail = "动作评分表现突出"
        elif score >= 75:
            detail = "本次动作评分达到稳定区间"
        else:
            detail = "本次更适合把动作质量放在速度之前"
        message = f"{nickname}，本次训练时长为 {duration:g}，{detail}（{score:g} 分）。"
        if unlocked:
            story = f"训练地图已记录你解锁的“{unlocked[-1]}”，下一段路线等待继续探索。"
        else:
            story = "训练地图记录了这次完成，下一枚路标将由稳定训练点亮。"
        return MotivationOutput(
            message=message,
            story=story,
            strategy="下一次只提高一个指标，同时保持动作质量。",
            next_goal=f"下一次保持至少 {duration:g} 的训练时长，并在动作稳定的前提下争取提高 2 分。",
        ).model_dump()

    def _number(self, value: int | float) -> float:
        try:
            return max(0.0, float(value))
        except (TypeError, ValueError):
            return 0.0


GameAgent = MotivationAgent
