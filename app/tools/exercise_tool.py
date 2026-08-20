from __future__ import annotations

import json
from typing import Any, Protocol

from app.llm.client import ToolSpec
from app.repositories import FitnessRepository, session_scope
from app.tools.registry import tool_result


class ExerciseStore(Protocol):
    def list(self, limit: int = 100) -> list[dict[str, Any]]: ...
    def get(self, exercise_id: int | None = None, name: str | None = None) -> dict[str, Any] | None: ...
    def save(self, data: dict[str, Any]) -> dict[str, Any] | None: ...
    def delete(self, exercise_id: int) -> bool: ...


class RepositoryExerciseStore:
    def list(self, limit: int = 100) -> list[dict[str, Any]]:
        with session_scope() as session:
            return FitnessRepository(session).exercises(limit=limit)

    def get(self, exercise_id: int | None = None, name: str | None = None) -> dict[str, Any] | None:
        for item in self.list(500):
            if exercise_id is not None and int(item["id"]) == int(exercise_id):
                return item
            if name and str(item.get("name") or "").strip() == str(name).strip():
                return item
        return None

    def save(self, data: dict[str, Any]) -> dict[str, Any] | None:
        with session_scope() as session:
            repo = FitnessRepository(session)
            exercise_id = repo.save_exercise(data)
            return next((item for item in repo.exercises(500) if item["id"] == exercise_id), None)

    def delete(self, exercise_id: int) -> bool:
        with session_scope() as session:
            return FitnessRepository(session).delete_exercise(exercise_id)


class ExerciseTool:
    def __init__(self, actor: dict[str, Any] | None = None, store: ExerciseStore | None = None):
        self.actor = dict(actor or {})
        self.store = store or RepositoryExerciseStore()

    def list_exercises(self, query: str = "", limit: int = 20) -> dict[str, Any]:
        """列出或搜索动作库动作。"""
        try:
            rows = self.store.list(self._limit(limit))
            text = str(query or "").strip().lower()
            if text:
                rows = [item for item in rows if text in self._search_text(item)]
            return tool_result(ok=True, mode="online", source="fitness-database", data={"exercises": rows})
        except Exception:
            return tool_result(ok=False, mode="fallback", source="fitness-database", fallback_reason="exercise_query_failed")

    def get_exercise(
        self,
        exercise_id: int | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        """通过 ID 或准确名称查询单个动作。"""
        if exercise_id is None and not str(name or "").strip():
            return tool_result(ok=False, mode="fallback", source="fitness-database", fallback_reason="exercise_identifier_required")
        try:
            item = self.store.get(exercise_id, name)
        except Exception:
            item = None
        if not item:
            return tool_result(ok=False, mode="online", source="fitness-database", fallback_reason="exercise_not_found")
        return tool_result(ok=True, mode="online", source="fitness-database", data={"exercise": item})

    def create_exercise(
        self,
        name: str,
        category: str = "综合训练",
        difficulty: int = 1,
        target: str = "综合体能",
        equipment: str = "徒手",
        standard: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """管理员创建动作；普通用户无权调用。"""
        denied = self._require_admin()
        if denied:
            return denied
        clean_name = str(name or "").strip()
        if not clean_name:
            return tool_result(ok=False, mode="local", source="exercise-admin", fallback_reason="exercise_name_required")
        if self.store.get(name=clean_name):
            return tool_result(ok=False, mode="online", source="fitness-database", fallback_reason="exercise_already_exists")
        item = self.store.save(self._payload(None, clean_name, category, difficulty, target, equipment, standard))
        return tool_result(ok=bool(item), mode="online", source="fitness-database", data={"exercise": item}, fallback_reason=None if item else "exercise_create_failed")

    def update_exercise(
        self,
        exercise_id: int,
        name: str | None = None,
        category: str | None = None,
        difficulty: int | None = None,
        target: str | None = None,
        equipment: str | None = None,
        standard: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """管理员更新已有动作；普通用户无权调用。"""
        denied = self._require_admin()
        if denied:
            return denied
        existing = self.store.get(exercise_id=exercise_id)
        if not existing:
            return tool_result(ok=False, mode="online", source="fitness-database", fallback_reason="exercise_not_found")
        current_standard = self._standard(existing.get("standard_json"))
        item = self.store.save(self._payload(
            int(exercise_id),
            name or existing["name"],
            category or existing.get("category") or "综合训练",
            difficulty if difficulty is not None else existing.get("difficulty", 1),
            target or existing.get("target") or "综合体能",
            equipment or existing.get("equipment") or "徒手",
            standard if standard is not None else current_standard,
        ))
        return tool_result(ok=bool(item), mode="online", source="fitness-database", data={"exercise": item}, fallback_reason=None if item else "exercise_update_failed")

    def delete_exercise(self, exercise_id: int, confirm: bool = False) -> dict[str, Any]:
        """管理员删除动作；必须显式传入 confirm=true。"""
        denied = self._require_admin()
        if denied:
            return denied
        if confirm is not True:
            return tool_result(ok=False, mode="local", source="exercise-admin", fallback_reason="delete_confirmation_required")
        if not self.store.get(exercise_id=exercise_id):
            return tool_result(ok=False, mode="online", source="fitness-database", fallback_reason="exercise_not_found")
        deleted = bool(self.store.delete(int(exercise_id)))
        return tool_result(ok=deleted, mode="online", source="fitness-database", data={"deleted": deleted, "exercise_id": int(exercise_id)}, fallback_reason=None if deleted else "exercise_delete_failed")

    def specs(self) -> list[ToolSpec]:
        common = {
            "name": {"type": "string"},
            "category": {"type": "string"},
            "difficulty": {"type": "integer", "minimum": 1, "maximum": 5},
            "target": {"type": "string"},
            "equipment": {"type": "string"},
            "standard": {"type": ["object", "null"]},
        }
        return [
            ToolSpec("list_exercises", "列出或搜索动作库。", self.list_exercises, {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 100}}, "required": [], "additionalProperties": False}),
            ToolSpec("get_exercise", "按 ID 或名称查询动作详情。", self.get_exercise, {"type": "object", "properties": {"exercise_id": {"type": ["integer", "null"]}, "name": {"type": ["string", "null"]}}, "required": [], "additionalProperties": False}),
            ToolSpec("create_exercise", "管理员创建动作。", self.create_exercise, {"type": "object", "properties": common, "required": ["name"], "additionalProperties": False}),
            ToolSpec("update_exercise", "管理员更新动作。", self.update_exercise, {"type": "object", "properties": {"exercise_id": {"type": "integer"}, **common}, "required": ["exercise_id"], "additionalProperties": False}),
            ToolSpec("delete_exercise", "管理员确认后删除动作。", self.delete_exercise, {"type": "object", "properties": {"exercise_id": {"type": "integer"}, "confirm": {"type": "boolean", "const": True}}, "required": ["exercise_id", "confirm"], "additionalProperties": False}),
        ]

    def _require_admin(self) -> dict[str, Any] | None:
        if self.actor.get("role") == "admin":
            return None
        return tool_result(ok=False, mode="local", source="exercise-admin", fallback_reason="admin_required")

    def _payload(self, exercise_id, name, category, difficulty, target, equipment, standard):
        return {
            "id": exercise_id,
            "name": str(name)[:100],
            "category": str(category)[:100],
            "difficulty": max(1, min(int(difficulty), 5)),
            "target": str(target)[:255],
            "equipment": str(equipment)[:255],
            "standard_json": json.dumps(standard or {}, ensure_ascii=False),
        }

    def _standard(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        try:
            parsed = json.loads(value or "{}")
            return parsed if isinstance(parsed, dict) else {}
        except (TypeError, json.JSONDecodeError):
            return {}

    def _search_text(self, item: dict[str, Any]) -> str:
        return " ".join(str(item.get(key) or "") for key in ("name", "category", "target", "equipment")).lower()

    def _limit(self, value: Any) -> int:
        try:
            return max(1, min(int(value), 100))
        except (TypeError, ValueError):
            return 20
