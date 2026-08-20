from __future__ import annotations

from app.tools.exercise_tool import ExerciseTool


class MemoryStore:
    def __init__(self):
        self.rows = [{"id": 1, "name": "深蹲", "category": "力量", "difficulty": 2, "target": "下肢", "equipment": "徒手", "standard_json": "{}"}]
        self.next_id = 2

    def list(self, limit=100):
        return [dict(item) for item in self.rows[:limit]]

    def get(self, exercise_id=None, name=None):
        return next((dict(item) for item in self.rows if (exercise_id is not None and item["id"] == int(exercise_id)) or (name and item["name"] == name)), None)

    def save(self, data):
        item = self.get(exercise_id=data.get("id")) if data.get("id") else None
        if item:
            target = next(row for row in self.rows if row["id"] == item["id"])
            target.update(data)
            return dict(target)
        row = {**data, "id": self.next_id}
        self.next_id += 1
        self.rows.append(row)
        return dict(row)

    def delete(self, exercise_id):
        before = len(self.rows)
        self.rows = [item for item in self.rows if item["id"] != int(exercise_id)]
        return len(self.rows) < before


def test_list_and_get_exercises():
    tool = ExerciseTool(actor={"role": "user"}, store=MemoryStore())
    listed = tool.list_exercises("深蹲")
    found = tool.get_exercise(name="深蹲")
    missing = tool.get_exercise(exercise_id=999)
    assert listed["data"]["exercises"][0]["name"] == "深蹲"
    assert found["data"]["exercise"]["id"] == 1
    assert missing["fallback_reason"] == "exercise_not_found"


def test_non_admin_cannot_create_update_or_delete():
    tool = ExerciseTool(actor={"id": 8, "role": "user"}, store=MemoryStore())
    assert tool.create_exercise("弓步")["fallback_reason"] == "admin_required"
    assert tool.update_exercise(1, name="新深蹲")["fallback_reason"] == "admin_required"
    assert tool.delete_exercise(1, confirm=True)["fallback_reason"] == "admin_required"


def test_admin_can_create_and_update_exercise():
    store = MemoryStore()
    tool = ExerciseTool(actor={"id": 1, "role": "admin"}, store=store)
    created = tool.create_exercise("弓步", target="下肢稳定")
    updated = tool.update_exercise(created["data"]["exercise"]["id"], difficulty=3)
    assert created["ok"] is True
    assert updated["data"]["exercise"]["difficulty"] == 3


def test_delete_requires_admin_and_explicit_confirmation():
    store = MemoryStore()
    tool = ExerciseTool(actor={"id": 1, "role": "admin"}, store=store)
    denied = tool.delete_exercise(1, confirm=False)
    deleted = tool.delete_exercise(1, confirm=True)
    assert denied["fallback_reason"] == "delete_confirmation_required"
    assert deleted["data"] == {"deleted": True, "exercise_id": 1}
    assert tool.get_exercise(exercise_id=1)["fallback_reason"] == "exercise_not_found"


def test_crud_tool_schemas_expose_permission_safe_delete_contract():
    specs = {item.name: item for item in ExerciseTool(store=MemoryStore()).specs()}
    assert set(specs) == {"list_exercises", "get_exercise", "create_exercise", "update_exercise", "delete_exercise"}
    assert specs["delete_exercise"].parameters["properties"]["confirm"]["const"] is True
    assert specs["delete_exercise"].parameters["required"] == ["exercise_id", "confirm"]
