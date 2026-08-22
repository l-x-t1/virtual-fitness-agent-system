"""Slot schema definitions for short-term fitness conversation state."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


GoalValue = Literal["减脂", "增肌", "塑形", "康复", "综合"]
InjuryValue = Literal["膝", "踝", "腰", "肩", "腕", "无"]
EquipmentValue = Literal["徒手", "弹力带", "哑铃", "健身房器械"]
TimeValue = Literal["早上", "午间", "晚上"]
LocationValue = Literal["家里", "健身房", "户外"]


class SlotValue(BaseModel):
    """Normalized slot value produced by extraction or fallback logic."""

    value: str
    source: str = "llm"


class SlotState(BaseModel):
    """Cross-turn slot tree stored in Redis and mirrored into conversation state."""

    goal: str | None = None
    target_body_part: str | None = None
    injuries: list[str] = Field(default_factory=list)
    equipment: str | None = None
    time: str | None = None
    location: str | None = None
    missing_required: list[str] = Field(default_factory=list)
    clarifying_rounds: int = 0
    clarified: bool = False
    awaiting_clarification: bool = False
    intent: str | None = None
    sub_intent: str | None = None
    intent_confidence: float = 0.0
    candidate_intents: list[str] = Field(default_factory=list)
    intent_reason: str | None = None
    conversation_context: dict[str, Any] = Field(default_factory=dict)
    source_turn_id: str | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def normalize(self):
        if isinstance(self.injuries, str):
            self.injuries = [self.injuries]
        self.injuries = self._normalize_injuries(self.injuries)
        self.goal = self._normalize_goal(self.goal)
        self.target_body_part = self._normalize_body_part(self.target_body_part)
        self.equipment = self._normalize_equipment(self.equipment)
        self.time = self._normalize_time(self.time)
        self.location = self._normalize_location(self.location)
        allowed_missing = {"intent", "goal", "target_body_part", "injuries", "equipment", "time", "location"}
        self.missing_required = [item for item in self.missing_required if item in allowed_missing]
        self.candidate_intents = [str(item) for item in self.candidate_intents if item]
        self.intent_confidence = max(0.0, min(1.0, float(self.intent_confidence or 0.0)))
        self.updated_at = self.updated_at if isinstance(self.updated_at, datetime) else datetime.now(timezone.utc)
        return self

    @staticmethod
    def required_keys() -> tuple[str, ...]:
        return ("goal", "injuries")

    @staticmethod
    def slot_names() -> tuple[str, ...]:
        return ("goal", "target_body_part", "injuries", "equipment", "time", "location")

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump()

    def merged(self, delta: dict[str, Any] | None = None) -> "SlotState":
        payload = self.model_dump()
        if delta:
            for key, value in delta.items():
                if value is None:
                    continue
                if key == "injuries":
                    payload[key] = self._merge_injuries(payload.get(key), value)
                elif key in payload:
                    payload[key] = value
        payload["updated_at"] = datetime.now(timezone.utc)
        return SlotState(**payload)

    def missing_required_slots(self, required_slots: list[str] | tuple[str, ...] | None = None) -> list[str]:
        required = tuple(required_slots) if required_slots is not None else self.required_keys()
        missing = []
        if "goal" in required and not self.goal:
            missing.append("goal")
        if "target_body_part" in required and not self.target_body_part:
            missing.append("target_body_part")
        if "injuries" in required and not self.injuries:
            missing.append("injuries")
        if "equipment" in required and not self.equipment:
            missing.append("equipment")
        if "time" in required and not self.time:
            missing.append("time")
        if "location" in required and not self.location:
            missing.append("location")
        return missing

    def set_missing_required(self, required_slots: list[str] | tuple[str, ...] | None = None) -> "SlotState":
        self.missing_required = self.missing_required_slots(required_slots)
        return self

    def complete(self, required_slots: list[str] | tuple[str, ...] | None = None) -> bool:
        return not self.missing_required_slots(required_slots)

    @staticmethod
    def _merge_injuries(current: Any, incoming: Any) -> list[str]:
        items = []
        for candidate in (current, incoming):
            if isinstance(candidate, str):
                items.append(candidate)
            elif isinstance(candidate, list):
                items.extend(str(item) for item in candidate)
            elif candidate:
                items.append(str(candidate))
        normalized: list[str] = []
        for item in items:
            for value in SlotState._normalize_injuries([item]):
                if value not in normalized:
                    normalized.append(value)
        return normalized

    @staticmethod
    def _normalize_goal(value: Any) -> str | None:
        text = str(value or "").strip()
        aliases = {
            "减肥": "减脂",
            "瘦身": "减脂",
            "塑型": "塑形",
            "康复训练": "康复",
            "恢复": "康复",
            "综合训练": "综合",
        }
        text = aliases.get(text, text)
        return text if text in {"减脂", "增肌", "塑形", "康复", "综合"} else None

    @staticmethod
    def _normalize_body_part(value: Any) -> str | None:
        text = str(value or "").strip()
        aliases = {
            "胸": "胸",
            "胸部": "胸",
            "练胸": "胸",
            "背": "背",
            "背部": "背",
            "腿": "腿",
            "腿部": "腿",
            "臀": "臀",
            "臀部": "臀",
            "肩": "肩",
            "肩部": "肩",
            "手臂": "手臂",
            "胳膊": "手臂",
            "核心": "核心",
            "腹": "核心",
            "腹部": "核心",
            "全身": "全身",
        }
        for needle, mapped in aliases.items():
            if needle in text:
                return mapped
        return text if text in {"胸", "背", "腿", "臀", "肩", "手臂", "核心", "全身"} else None

    @staticmethod
    def _normalize_injuries(values: Any) -> list[str]:
        if values is None:
            return []
        if isinstance(values, str):
            values = [values]
        mapping = {
            "膝盖": "膝",
            "膝关节": "膝",
            "knee": "膝",
            "踝关节": "踝",
            "脚踝": "踝",
            "ankle": "踝",
            "腰部": "腰",
            "lower back": "腰",
            "肩部": "肩",
            "shoulder": "肩",
            "手腕": "腕",
            "wrist": "腕",
            "无": "无",
            "没有": "无",
            "无伤病": "无",
        }
        normalized: list[str] = []
        for raw in values:
            text = str(raw or "").strip()
            if not text:
                continue
            for needle, mapped in mapping.items():
                if needle.lower() in text.lower():
                    text = mapped
                    break
            if text in {"膝", "踝", "腰", "肩", "腕", "无"} and text not in normalized:
                normalized.append(text)
        if "无" in normalized and len(normalized) > 1:
            normalized = [item for item in normalized if item != "无"]
        return normalized

    @staticmethod
    def _normalize_equipment(value: Any) -> str | None:
        text = str(value or "").strip()
        aliases = {
            "无器材": "徒手",
            "徒手训练": "徒手",
            "器械": "健身房器械",
            "健身器械": "健身房器械",
            "gym": "健身房器械",
        }
        text = aliases.get(text, text)
        return text if text in {"徒手", "弹力带", "哑铃", "健身房器械"} else None

    @staticmethod
    def _normalize_time(value: Any) -> str | None:
        text = str(value or "").strip()
        aliases = {"早晨": "早上", "中午": "午间", "傍晚": "晚上"}
        text = aliases.get(text, text)
        return text if text in {"早上", "午间", "晚上"} else None

    @staticmethod
    def _normalize_location(value: Any) -> str | None:
        text = str(value or "").strip()
        aliases = {"家中": "家里", "健身馆": "健身房"}
        text = aliases.get(text, text)
        return text if text in {"家里", "健身房", "户外"} else None

