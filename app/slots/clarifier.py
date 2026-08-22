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

    def decide(
        self,
        state: SlotState,
        *,
        extracted: dict[str, Any] | None = None,
        required_slots: list[str] | tuple[str, ...] | None = None,
    ) -> ClarifyDecision:
        current = SlotState(**state.model_dump())
        missing = current.missing_required_slots(required_slots)
        current.clarifying_rounds += 1 if missing else 0
        current.set_missing_required(required_slots)
        if not current.missing_required:
            current.clarified = True
            current.awaiting_clarification = False
            return ClarifyDecision("continue", "", current)
        if current.clarifying_rounds > self.max_rounds:
            current.awaiting_clarification = False
            return ClarifyDecision("fallback", self._fallback_message(current), current, should_fallback=True)
        current.awaiting_clarification = True
        return ClarifyDecision("clarify", self._question_for(current), current)

    def _question_for(self, state: SlotState) -> str:
        missing = state.missing_required
        prompts = []
        if "goal" in missing:
            prompts.append("你这次更想减脂、增肌、塑形、康复还是综合训练？")
        if "target_body_part" in missing:
            prompts.append("主要想练哪个部位，比如胸、背、腿、肩、核心或全身？")
        if "injuries" in missing:
            prompts.append("你的伤病红线是膝、踝、腰、肩、腕，还是没有？")
        if "equipment" in missing:
            prompts.append("你现在可用的器械是徒手、弹力带、哑铃还是健身房器械？")
        if "time" in missing:
            prompts.append("你更方便早上、午间还是晚上训练？")
        if "location" in missing:
            prompts.append("训练地点是在家里、健身房还是户外？")
        return "；".join(prompts[:2]) or "请补充必要信息。"

    def _fallback_message(self, state: SlotState) -> str:
        missing = state.missing_required or state.missing_required_slots()
        return (
            "已超过澄清次数，系统将按当前可用信息进入安全兜底。"
            f"当前缺失：{', '.join(missing) or '无'}。"
        )

