"""
数据导入模块：从 PostgreSQL/SQLite 读取数据并同步到 Neo4j

使用方式:
  - 一键全量导入: python -m app.graph.data_import --full
  - 增量同步用户: python -m app.graph.data_import --user 1
  - 在代码中调用: from app.graph.data_import import import_all; import_all()
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.graph.neo4j_client import is_available, run_write
from app.graph.queries import (
    LINK_EXERCISE_ACHIEVES_GOAL,
    LINK_EXERCISE_REQUIRES_EQUIPMENT,
    LINK_EXERCISE_TARGETS_MUSCLE,
    LINK_USER_PREFERS_GOAL,
    LINK_VENUE_HAS_EQUIPMENT,
    MERGE_EQUIPMENT,
    MERGE_EXERCISE,
    MERGE_USER,
    MERGE_VENUE,
)
from app.repositories import FitnessRepository, session_scope

logger = logging.getLogger("fitness.import")

# 器材名称 → 器材节点映射（用于创建 RELATIONSHIP）
EQUIPMENT_NODE_MAP: dict[str, str] = {
    "徒手": "徒手训练",
    "瑜伽垫": "瑜伽垫",
    "跑道": "跑道",
    "力量器械": "力量器械",
    "智能器材": "智能器材",
}

# 动作 → 目标肌群映射
EXERCISE_MUSCLE_MAP: dict[str, list[tuple[str, float]]] = {
    "深蹲": [("下肢力量", 0.9), ("核心稳定", 0.5), ("全身协调", 0.3)],
    "平板支撑": [("核心稳定", 0.95)],
    "开合跳": [("心肺耐力", 0.85), ("全身协调", 0.7), ("下肢力量", 0.3)],
    "弓步蹲": [("下肢协调", 0.9), ("下肢力量", 0.7), ("核心稳定", 0.5)],
    "节奏冲刺": [("爆发力", 0.9), ("心肺耐力", 0.8), ("下肢力量", 0.6)],
}

# 动作 → 达成目标映射
EXERCISE_GOAL_MAP: dict[str, list[tuple[str, float]]] = {
    "深蹲": [("增肌", 0.8), ("综合训练", 0.6), ("减脂", 0.4)],
    "平板支撑": [("综合训练", 0.7), ("柔韧性", 0.3)],
    "开合跳": [("减脂", 0.9), ("耐力提升", 0.8), ("协调性", 0.7)],
    "弓步蹲": [("协调性", 0.9), ("增肌", 0.6), ("综合训练", 0.5)],
    "节奏冲刺": [("爆发力", 0.95), ("耐力提升", 0.7), ("减脂", 0.6)],
}

# 偏好 → Goal 映射
PREFERENCE_GOAL_MAP: dict[str, list[str]] = {
    "力量训练": ["增肌"],
    "有氧训练": ["减脂", "耐力提升"],
    "核心训练": ["综合训练"],
    "柔韧性训练": ["柔韧性"],
    "综合训练": ["综合训练", "协调性"],
    "爆发力训练": ["爆发力"],
}

# 场地拥有的器材（按场地名称）
VENUE_EQUIPMENT_MAP: dict[str, list[str]] = {
    "徒手": ["徒手训练"],
    "跑道": ["跑道"],
    "力量器械": ["力量器械"],
    "瑜伽垫": ["瑜伽垫"],
    "智能器材": ["智能器材"],
}


@dataclass
class ImportStats:
    users: int = 0
    exercises: int = 0
    venues: int = 0
    equipment: int = 0
    relationships: int = 0
    errors: list[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []

    @property
    def total(self) -> int:
        return self.users + self.exercises + self.venues + self.equipment + self.relationships


def _ensure_equipment_nodes() -> int:
    """确保所有预定义器材节点存在"""
    count = 0
    predefined = [
        ("徒手训练", "基础", False),
        ("瑜伽垫", "辅助", False),
        ("跑道", "场地", False),
        ("力量器械", "力量", False),
        ("智能器材", "智能", True),
    ]
    for eq_id, (name, category, is_smart) in enumerate(predefined, start=1):
        run_write(
            MERGE_EQUIPMENT,
            {
                "equipment_id": eq_id,
                "name": name,
                "category": category,
                "is_smart": is_smart,
                "status": "normal",
                "location": "",
                "latitude": 0.0,
                "longitude": 0.0,
                "venue_id": None,
            },
        )
        count += 1
    return count


def _parse_equipment_list(equipment_str: str) -> list[str]:
    """解析器材字符串（逗号/顿号分隔）为器材名称列表"""
    items = []
    for item in equipment_str.replace("，", ",").split(","):
        item = item.strip()
        if item and item in EQUIPMENT_NODE_MAP:
            items.append(EQUIPMENT_NODE_MAP[item])
        elif item:
            items.append(item)
    return items


def _resolve_goals_from_preference(preference: str) -> list[str]:
    """根据用户 preference 字符串解析出 Goal 列表"""
    goals = []
    for key, goal_list in PREFERENCE_GOAL_MAP.items():
        if key in preference:
            goals.extend(goal_list)
    return list(set(goals)) or ["综合训练"]


def import_users() -> int:
    with session_scope() as session:
        users = FitnessRepository(session).graph_users()

    count = 0
    for u in users:
        params = {
            "user_id": u["id"],
            "nickname": u.get("nickname") or "",
            "age": u.get("age") or 20,
            "fitness_level": u.get("fitness_level") or "beginner",
            "injuries": u.get("injuries") or "",
            "preference": u.get("preference") or "综合训练",
            "location": u.get("location") or "",
            "points": u.get("points") or 0,
            "level": u.get("level") or 1,
        }
        run_write(MERGE_USER, params)

        # 创建 User → Goal 偏好关系
        goals = _resolve_goals_from_preference(params["preference"])
        for goal_name in goals:
            run_write(LINK_USER_PREFERS_GOAL, {"user_id": params["user_id"], "goal_name": goal_name})

        count += 1
    return count


def import_exercises() -> int:
    with session_scope() as session:
        exercises = FitnessRepository(session).graph_exercises()

    count = 0
    for ex in exercises:
        name = ex["name"]
        params = {
            "exercise_id": ex["id"],
            "name": name,
            "category": ex.get("category") or "",
            "difficulty": ex.get("difficulty") or 1,
            "target": ex.get("target") or "",
            "equipment": ex.get("equipment") or "",
            "standard_json": ex.get("standard_json") or "{}",
        }
        run_write(MERGE_EXERCISE, params)

        # 创建 Exercise → MuscleGroup 关系
        for muscle_name, weight in EXERCISE_MUSCLE_MAP.get(name, []):
            run_write(LINK_EXERCISE_TARGETS_MUSCLE, {
                "exercise_name": name, "muscle_name": muscle_name, "weight": weight,
            })

        # 创建 Exercise → Goal 关系
        for goal_name, effectiveness in EXERCISE_GOAL_MAP.get(name, []):
            run_write(LINK_EXERCISE_ACHIEVES_GOAL, {
                "exercise_name": name, "goal_name": goal_name, "effectiveness": effectiveness,
            })

        # 创建 Exercise → Equipment 关系
        equipment_names = _parse_equipment_list(params["equipment"])
        for eq_name in equipment_names:
            run_write(LINK_EXERCISE_REQUIRES_EQUIPMENT, {
                "exercise_name": name, "equipment_name": eq_name, "priority": "required",
            })

        count += 1
    return count


def import_venues() -> int:
    with session_scope() as session:
        venues = FitnessRepository(session).graph_venues()

    count = 0
    for v in venues:
        params = {
            "venue_id": v["id"],
            "name": v["name"],
            "location": v.get("location") or "",
            "latitude": v.get("latitude"),
            "longitude": v.get("longitude"),
            "equipment": v.get("equipment") or "",
            "capacity": v.get("capacity") or 0,
            "crowd_index": v.get("crowd_index") or 50,
            "air_quality": v.get("air_quality") or 50,
            "rating": v.get("rating") or 4.0,
            "density_score": v.get("density_score") or 0.0,
            "kind": v.get("kind") or "outdoor",
            "open_hours": v.get("open_hours") or "",
        }
        run_write(MERGE_VENUE, params)

        # 创建 Venue → Equipment 关系
        equipment_names = _parse_equipment_list(params["equipment"])
        for i, eq_name in enumerate(equipment_names, start=1):
            run_write(LINK_VENUE_HAS_EQUIPMENT, {
                "venue_id": params["venue_id"],
                "equipment_id": i,  # 匹配预定义的器材 ID
                "quantity": 1,
            })

        count += 1
    return count


def import_all() -> ImportStats:
    """全量导入：用户、动作、场地及关系"""
    stats = ImportStats()

    if not is_available():
        stats.errors.append("Neo4j is not available; check NEO4J_URI in .env")
        return stats

    try:
        _ensure_equipment_nodes()
        stats.equipment = len(EQUIPMENT_NODE_MAP)
    except Exception as exc:
        stats.errors.append(f"equipment: {exc}")

    try:
        stats.users = import_users()
        logger.info("Imported %d users", stats.users)
    except Exception as exc:
        stats.errors.append(f"users: {exc}")
        logger.exception("User import failed")

    try:
        stats.exercises = import_exercises()
        logger.info("Imported %d exercises", stats.exercises)
    except Exception as exc:
        stats.errors.append(f"exercises: {exc}")
        logger.exception("Exercise import failed")

    try:
        stats.venues = import_venues()
        logger.info("Imported %d venues", stats.venues)
    except Exception as exc:
        stats.errors.append(f"venues: {exc}")
        logger.exception("Venue import failed")

    return stats


# ---- CLI ----
if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(description="Import data from DB to Neo4j")
    parser.add_argument("--full", action="store_true", help="Full import")
    parser.add_argument("--stats", action="store_true", help="Show import stats only")
    args = parser.parse_args()

    if args.stats:
        from app.graph.neo4j_client import run_read
        from app.graph.queries import GRAPH_STATS
        result = run_read(GRAPH_STATS)
        print(result)
    elif args.full:
        result = import_all()
        print(f"Imported: {result.users} users, {result.exercises} exercises, "
              f"{result.venues} venues, {result.equipment} equipment")
        if result.errors:
            print(f"Errors: {result.errors}")
    else:
        parser.print_help()
