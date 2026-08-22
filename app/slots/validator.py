"""Slot value validation and injury conflict resolution."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.graph.neo4j_client import is_available, run_read
from app.slots.models import SlotState


@dataclass
class ValidationResult:
    valid: bool
    state: SlotState
    errors: list[str] = field(default_factory=list)
    replacements: list[dict[str, Any]] = field(default_factory=list)


class SlotValidator:
    def validate(self, state: SlotState) -> ValidationResult:
        normalized = SlotState(**state.model_dump())
        errors: list[str] = []
        if normalized.goal is None:
            errors.append("goal_missing")
        if not normalized.injuries:
            errors.append("injuries_missing")
        if normalized.goal and normalized.goal not in {"减脂", "增肌", "塑形", "康复", "综合"}:
            errors.append("goal_invalid")
        if normalized.equipment and normalized.equipment not in {"徒手", "弹力带", "哑铃", "健身房器械"}:
            errors.append("equipment_invalid")
        if normalized.time and normalized.time not in {"早上", "午间", "晚上"}:
            errors.append("time_invalid")
        if normalized.location and normalized.location not in {"家里", "健身房", "户外"}:
            errors.append("location_invalid")
        return ValidationResult(valid=not errors, state=normalized, errors=errors)

    def resolve_exercises(self, exercises: list[dict[str, Any]], state: SlotState) -> list[dict[str, Any]]:
        if not exercises:
            return []
        injuries = set(state.injuries)
        resolved = []
        for item in exercises:
            if self._has_conflict(item, injuries):
                replacement = self._replacement_for(item, state)
                if replacement:
                    resolved.append(replacement)
                    continue
            resolved.append(item)
        return resolved

    def _has_conflict(self, exercise: dict[str, Any], injuries: set[str]) -> bool:
        exercise_name = str(exercise.get("name") or "")
        risky = {
            "深蹲": {"膝", "踝"},
            "弓步蹲": {"膝"},
            "开合跳": {"膝", "踝"},
            "节奏冲刺": {"膝", "踝"},
            "平板支撑": {"腰"},
        }
        target = risky.get(exercise_name, set())
        return bool(target & injuries)

    def _replacement_for(self, exercise: dict[str, Any], state: SlotState) -> dict[str, Any] | None:
        if not is_available():
            return {**exercise, "name": f"{exercise.get('name')}（低冲击替代）", "replacement_of": exercise.get("name")}
        body_map = {
            "膝": "膝关节",
            "踝": "踝关节",
            "腰": "核心稳定",
            "肩": "肩关节",
            "腕": "手腕",
        }
        keywords = [body_map.get(item, item) for item in state.injuries if item != "无"]
        if not keywords:
            return None
        rows = run_read(
            """
            MATCH (e:Exercise)-[:INVOLVES]->(b:BodyPart)
            WHERE any(keyword IN $keywords WHERE b.name CONTAINS keyword)
            RETURN e AS exercise
            LIMIT 20
            """,
            {"keywords": keywords},
        )
        for row in rows:
            candidate = row.get("exercise") or row.get("e") or {}
            if candidate and str(candidate.get("name") or "") != str(exercise.get("name") or ""):
                return {
                    "name": candidate.get("name"),
                    "category": candidate.get("category"),
                    "equipment": candidate.get("equipment"),
                    "target": candidate.get("target"),
                    "replacement_of": exercise.get("name"),
                }
        return {**exercise, "name": f"{exercise.get('name')}（低冲击替代）", "replacement_of": exercise.get("name")}

