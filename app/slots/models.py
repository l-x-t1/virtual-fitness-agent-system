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
    injuries: list[str] = Field(default_factory=list)
    equipment: str | None = None
    time: str | None = None
    location: str | None = None
    missing_required: list[str] = Field(default_factory=list)
    clarifying_rounds: int = 0
    clarified: bool = False
    source_turn_id: str | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def normalize(self):
        if isinstance(self.injuries, str):
            self.injuries = [self.injuries]
        self.injuries = self._normalize_injuries(self.injuries)
        self.goal = self._normalize_goal(self.goal)
        self.equipment = self._normalize_equipment(self.equipment)
        self.time = self._normalize_time(self.time)
        self.location = self._normalize_location(self.location)
        self.missing_required = [item for item in self.missing_required if item in {"goal", "injuries"}]
        self.updated_at = self.updated_at if isinstance(self.updated_at, datetime) else datetime.now(timezone.utc)
        return self

    @staticmethod
    def required_keys() -> tuple[str, ...]:
        return ("goal", "injuries")

    @staticmethod
    def slot_names() -> tuple[str, ...]:
        return ("goal", "injuries", "equipment", "time", "location")

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

    def missing_required_slots(self) -> list[str]:
        missing = []
        if not self.goal:
            missing.append("goal")
        if not self.injuries:
            missing.append("injuries")
        return missing

    def set_missing_required(self) -> "SlotState":
        self.missing_required = self.missing_required_slots()
        return self

    def complete(self) -> bool:
        return not self.missing_required_slots()

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

