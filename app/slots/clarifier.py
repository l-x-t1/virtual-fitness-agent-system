"""Clarification logic for incomplete required slots."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.slots.models import SlotState


@dataclass
class ClarifyDecision:
    action: str
    message: str
    state: SlotState
    should_fallback: bool = False


class SlotClarifier:
    def __init__(self, max_rounds: int = 2):
        self.max_rounds = max_rounds

    def decide(self, state: SlotState, *, extracted: dict[str, Any] | None = None) -> ClarifyDecision:
        current = SlotState(**state.model_dump())
        current.clarifying_rounds += 1 if current.missing_required_slots() else 0
        current.set_missing_required()
        if not current.missing_required:
            current.clarified = True
            return ClarifyDecision("continue", "", current)
        if current.clarifying_rounds > self.max_rounds:
            return ClarifyDecision("fallback", self._fallback_message(current), current, should_fallback=True)
        return ClarifyDecision("clarify", self._question_for(current), current)

    def _question_for(self, state: SlotState) -> str:
        missing = state.missing_required_slots()
        prompts = []
        if "goal" in missing:
            prompts.append("你这次更想减脂、增肌、塑形、康复还是综合训练？")
        if "injuries" in missing:
            prompts.append("你的伤病红线是膝、踝、腰、肩、腕，还是没有？")
        return "；".join(prompts) or "请补充必要信息。"

    def _fallback_message(self, state: SlotState) -> str:
        return (
            "已超过澄清次数，系统将按当前可用信息进入安全兜底。"
            f"当前缺失：{', '.join(state.missing_required_slots()) or '无'}。"
        )

