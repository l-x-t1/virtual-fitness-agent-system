"""Import business and domain fitness knowledge into Neo4j.

The import is additive and scoped to the graph module. It reads the existing
business database through SQLAlchemy, loads the JSON fitness knowledge base,
and writes Neo4j nodes/relationships defined in app.graph.graph_schema.
"""

from __future__ import annotations

import json
import logging
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.graph.graph_schema import initialize_graph_schema
from app.graph.neo4j_client import Neo4jClient, is_available
from app.repositories import session_scope

logger = logging.getLogger("fitness.import")

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_KNOWLEDGE_PATH = BASE_DIR / "knowledge_base" / "fitness_knowledge.json"


@dataclass
class ImportStats:
    users: int = 0
    exercises: int = 0
    venues: int = 0
    equipment: int = 0
    training_records: int = 0
    knowledge_items: int = 0
    relationships: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return (
            self.users
            + self.exercises
            + self.venues
            + self.equipment
            + self.training_records
            + self.knowledge_items
            + self.relationships
        )


def load_knowledge_base(path: str | Path = DEFAULT_KNOWLEDGE_PATH) -> dict[str, Any]:
    """Load and validate the structured fitness knowledge JSON."""
    file_path = Path(path)
    data = json.loads(file_path.read_text(encoding="utf-8"))
    if not isinstance(data.get("exercises"), list):
        raise ValueError("fitness knowledge base must contain an exercises list")
    for exercise in data["exercises"]:
        for key in ("name", "standard_action", "errors"):
            if key not in exercise:
                raise ValueError(f"exercise item is missing required field: {key}")
    return data


def import_all(include_reference_data: bool = True) -> ImportStats:
    """Full graph import used by API and CLI entry points."""
    stats = ImportStats()

    if not is_available():
        stats.errors.append("Neo4j is not available; check NEO4J_URI in .env and start the database.")
        return stats

    client = Neo4jClient()
    try:
        schema_result = initialize_graph_schema(client=client, include_reference_data=include_reference_data)
        stats.errors.extend(schema_result.get("errors", []))

        stats.knowledge_items += import_knowledge_base(client=client)
        business_stats = import_business_data(client=client)
        _merge_stats(stats, business_stats)
    finally:
        client.close()

    return stats


def import_business_data(client: Neo4jClient | None = None) -> ImportStats:
    """Import existing SQLAlchemy business data into the graph."""
    client = client or Neo4jClient()
    stats = ImportStats()

    try:
        stats.users = import_users(client)
    except Exception as exc:
        stats.errors.append(f"users: {exc}")
        logger.exception("User import failed")

    try:
        stats.exercises += import_exercises_from_db(client)
    except Exception as exc:
        stats.errors.append(f"exercises: {exc}")
        logger.exception("Exercise import failed")

    try:
        venue_stats = import_venues_and_equipment(client)
        stats.venues += venue_stats.venues
        stats.equipment += venue_stats.equipment
        stats.relationships += venue_stats.relationships
    except Exception as exc:
        stats.errors.append(f"venues/equipment: {exc}")
        logger.exception("Venue import failed")

    try:
        record_stats = import_training_records(client)
        stats.training_records += record_stats.training_records
        stats.relationships += record_stats.relationships
    except Exception as exc:
        stats.errors.append(f"training_records: {exc}")
        logger.exception("Training record import failed")

    return stats


def import_users(client: Neo4jClient) -> int:
    with session_scope() as session:
        rows = session.execute(
            text(
                "SELECT id, nickname, age, fitness_level, injuries, preference, location, points, level "
                "FROM users"
            )
        )
        users = [dict(row._mapping) for row in rows]

    for user in users:
        client.execute_cypher(
            """
            MERGE (u:User {user_id: $user_id})
            SET u.nickname = $nickname,
                u.age = $age,
                u.fitness_level = $fitness_level,
                u.injuries = $injuries,
                u.preference = $preference,
                u.location = $location,
                u.points = $points,
                u.level = $level
            WITH u
            MATCH (l:Level {name: $fitness_level})
            MERGE (u)-[:HAS_LEVEL]->(l)
            """,
            {
                "user_id": int(user["id"]),
                "nickname": user.get("nickname") or "",
                "age": user.get("age") or 20,
                "fitness_level": user.get("fitness_level") or "beginner",
                "injuries": user.get("injuries") or "",
                "preference": user.get("preference") or "",
                "location": user.get("location") or "",
                "points": user.get("points") or 0,
                "level": user.get("level") or 1,
            },
            readonly=False,
        )

        for goal_name in _resolve_goals_from_text(user.get("preference") or ""):
            client.execute_cypher(
                """
                MATCH (u:User {user_id: $user_id})
                MERGE (g:Goal {name: $goal_name})
                MERGE (u)-[:HAS_GOAL]->(g)
                MERGE (u)-[:PREFERS]->(g)
                """,
                {"user_id": int(user["id"]), "goal_name": goal_name},
                readonly=False,
            )

    return len(users)


def import_exercises_from_db(client: Neo4jClient) -> int:
    with session_scope() as session:
        rows = session.execute(
            text("SELECT id, name, category, difficulty, target, equipment, standard_json FROM exercises")
        )
        exercises = [dict(row._mapping) for row in rows]

    for exercise in exercises:
        equipment_names = _split_names(exercise.get("equipment") or "")
        client.execute_cypher(
            """
            MERGE (e:Exercise {name: $name})
            SET e.exercise_id = $exercise_id,
                e.category = $category,
                e.difficulty = $difficulty,
                e.target = $target,
                e.equipment = $equipment,
                e.standard_json = $standard_json
            """,
            {
                "exercise_id": exercise["id"],
                "name": exercise["name"],
                "category": exercise.get("category") or "",
                "difficulty": exercise.get("difficulty") or 1,
                "target": exercise.get("target") or "",
                "equipment": exercise.get("equipment") or "",
                "standard_json": exercise.get("standard_json") or "{}",
            },
            readonly=False,
        )
        for equipment_name in equipment_names:
            _merge_equipment(client, equipment_name)
            client.execute_cypher(
                """
                MATCH (e:Exercise {name: $exercise_name})
                MATCH (eq:Equipment {name: $equipment_name})
                MERGE (e)-[:USES]->(eq)
                MERGE (e)-[:REQUIRES {priority: 'required'}]->(eq)
                """,
                {"exercise_name": exercise["name"], "equipment_name": equipment_name},
                readonly=False,
            )

    return len(exercises)


def import_venues_and_equipment(client: Neo4jClient) -> ImportStats:
    stats = ImportStats()
    with session_scope() as session:
        rows = session.execute(
            text(
                "SELECT id, name, location, latitude, longitude, equipment, capacity, crowd_index, "
                "air_quality, rating, density_score, kind, open_hours FROM venues"
            )
        )
        venues = [dict(row._mapping) for row in rows]

        equipment_rows = session.execute(
            text(
                "SELECT id, name, category, venue_id, location, latitude, longitude, is_smart, status "
                "FROM fitness_equipment"
            )
        )
        equipment_items = [dict(row._mapping) for row in equipment_rows]

    for venue in venues:
        client.execute_cypher(
            """
            MERGE (v:Venue {venue_id: $venue_id})
            SET v.name = $name,
                v.location = $location,
                v.latitude = $latitude,
                v.longitude = $longitude,
                v.equipment = $equipment,
                v.capacity = $capacity,
                v.crowd_index = $crowd_index,
                v.air_quality = $air_quality,
                v.rating = $rating,
                v.density_score = $density_score,
                v.kind = $kind,
                v.open_hours = $open_hours
            """,
            {
                "venue_id": venue["id"],
                "name": venue["name"],
                "location": venue.get("location") or "",
                "latitude": venue.get("latitude"),
                "longitude": venue.get("longitude"),
                "equipment": venue.get("equipment") or "",
                "capacity": venue.get("capacity") or 0,
                "crowd_index": venue.get("crowd_index") or 50,
                "air_quality": venue.get("air_quality") or 50,
                "rating": venue.get("rating") or 4.0,
                "density_score": venue.get("density_score") or 0.0,
                "kind": venue.get("kind") or "outdoor",
                "open_hours": venue.get("open_hours") or "",
            },
            readonly=False,
        )
        stats.venues += 1

        for equipment_name in _split_names(venue.get("equipment") or ""):
            equipment_id = _merge_equipment(client, equipment_name)
            client.execute_cypher(
                """
                MATCH (v:Venue {venue_id: $venue_id})
                MATCH (eq:Equipment {equipment_id: $equipment_id})
                MERGE (v)-[:HAS_EQUIPMENT {quantity: 1}]->(eq)
                """,
                {"venue_id": venue["id"], "equipment_id": equipment_id},
                readonly=False,
            )
            stats.relationships += 1

    for equipment in equipment_items:
        client.execute_cypher(
            """
            MERGE (eq:Equipment {equipment_id: $equipment_id})
            SET eq.name = $name,
                eq.category = $category,
                eq.venue_id = $venue_id,
                eq.location = $location,
                eq.latitude = $latitude,
                eq.longitude = $longitude,
                eq.is_smart = $is_smart,
                eq.status = $status
            WITH eq
            OPTIONAL MATCH (v:Venue {venue_id: $venue_id})
            FOREACH (_ IN CASE WHEN v IS NULL THEN [] ELSE [1] END |
                MERGE (v)-[:HAS_EQUIPMENT {quantity: 1}]->(eq)
            )
            """,
            {
                "equipment_id": equipment["id"],
                "name": equipment["name"],
                "category": equipment.get("category") or "",
                "venue_id": equipment.get("venue_id"),
                "location": equipment.get("location") or "",
                "latitude": equipment.get("latitude"),
                "longitude": equipment.get("longitude"),
                "is_smart": bool(equipment.get("is_smart")),
                "status": equipment.get("status") or "normal",
            },
            readonly=False,
        )
        stats.equipment += 1

    return stats


def import_training_records(client: Neo4jClient) -> ImportStats:
    stats = ImportStats()
    with session_scope() as session:
        rows = session.execute(
            text(
                "SELECT id, user_id, exercise_name, score, duration, feedback, created_at "
                "FROM sessions ORDER BY created_at DESC"
            )
        )
        records = [dict(row._mapping) for row in rows]

    for record in records:
        record_id = f"session:{record['id']}"
        client.execute_cypher(
            """
            MERGE (r:TrainingRecord {record_id: $record_id})
            SET r.session_id = $session_id,
                r.user_id = $user_id,
                r.exercise_name = $exercise_name,
                r.score = $score,
                r.duration = $duration,
                r.feedback = $feedback,
                r.created_at = $created_at
            WITH r
            MATCH (u:User {user_id: $user_id})
            MERGE (u)-[:HAS_RECORD]->(r)
            WITH r
            MATCH (e:Exercise {name: $exercise_name})
            MERGE (r)-[:CONTAINS]->(e)
            """,
            {
                "record_id": record_id,
                "session_id": record["id"],
                "user_id": record["user_id"],
                "exercise_name": record["exercise_name"],
                "score": record.get("score") or 0,
                "duration": record.get("duration") or 0,
                "feedback": record.get("feedback") or "",
                "created_at": str(record.get("created_at") or ""),
            },
            readonly=False,
        )
        stats.training_records += 1
        stats.relationships += 2

        if int(record.get("score") or 0) < 75:
            linked = _link_first_exercise_error_to_record(client, record_id, record["exercise_name"])
            stats.relationships += linked

    return stats


def import_knowledge_base(
    client: Neo4jClient | None = None,
    path: str | Path = DEFAULT_KNOWLEDGE_PATH,
) -> int:
    """Import domain exercise/error/correction knowledge from JSON."""
    client = client or Neo4jClient()
    knowledge = load_knowledge_base(path)
    count = 0

    for exercise in knowledge["exercises"]:
        equipment_names = exercise.get("equipment", [])
        target_text = ",".join(exercise.get("muscles", []))
        client.execute_cypher(
            """
            MERGE (e:Exercise {name: $name})
            SET e.category = $category,
                e.difficulty = $difficulty,
                e.target = $target,
                e.equipment = $equipment,
                e.standard_action = $standard_action,
                e.precautions = $precautions
            """,
            {
                "name": exercise["name"],
                "category": exercise.get("category") or "",
                "difficulty": exercise.get("difficulty") or 1,
                "target": target_text,
                "equipment": ",".join(equipment_names),
                "standard_action": exercise.get("standard_action") or "",
                "precautions": exercise.get("precautions") or "",
            },
            readonly=False,
        )
        count += 1

        _link_exercise_level(client, exercise["name"], exercise.get("level") or "beginner")
        count += _link_exercise_body_parts(client, exercise["name"], exercise.get("body_parts", []))
        count += _link_exercise_muscles(client, exercise["name"], exercise.get("muscles", []))
        count += _link_exercise_equipment(client, exercise["name"], equipment_names)
        count += _link_exercise_goals(client, exercise["name"], exercise.get("goals", []))
        count += _import_exercise_errors(client, exercise["name"], exercise.get("errors", []))

    for plan in knowledge.get("training_plans", []):
        client.execute_cypher(
            """
            MERGE (g:Goal {name: $goal})
            SET g.description = $description,
                g.recommendation = $recommendation
            """,
            {
                "goal": plan["goal"],
                "description": plan.get("description") or "",
                "recommendation": plan.get("recommendation") or "",
            },
            readonly=False,
        )
        count += 1

    return count


def _link_exercise_level(client: Neo4jClient, exercise_name: str, level_name: str) -> None:
    client.execute_cypher(
        """
        MATCH (e:Exercise {name: $exercise_name})
        MERGE (l:Level {name: $level_name})
        MERGE (e)-[:SUITABLE_LEVEL]->(l)
        """,
        {"exercise_name": exercise_name, "level_name": level_name},
        readonly=False,
    )


def _link_exercise_body_parts(client: Neo4jClient, exercise_name: str, body_parts: list[str]) -> int:
    for body_part in body_parts:
        client.execute_cypher(
            """
            MERGE (b:BodyPart {name: $body_part})
            WITH b
            MATCH (e:Exercise {name: $exercise_name})
            MERGE (e)-[:INVOLVES]->(b)
            """,
            {"exercise_name": exercise_name, "body_part": body_part},
            readonly=False,
        )
    return len(body_parts)


def _link_exercise_muscles(client: Neo4jClient, exercise_name: str, muscles: list[str]) -> int:
    for muscle in muscles:
        client.execute_cypher(
            """
            MERGE (m:Muscle {name: $muscle})
            WITH m
            OPTIONAL MATCH (b:BodyPart {name: m.body_part})
            FOREACH (_ IN CASE WHEN b IS NULL THEN [] ELSE [1] END |
                MERGE (m)-[:LOCATED_IN]->(b)
            )
            WITH m
            MATCH (e:Exercise {name: $exercise_name})
            MERGE (e)-[:TARGETS {weight: 1.0}]->(m)
            """,
            {"exercise_name": exercise_name, "muscle": muscle},
            readonly=False,
        )
    return len(muscles)


def _link_exercise_equipment(client: Neo4jClient, exercise_name: str, equipment_names: list[str]) -> int:
    for equipment_name in equipment_names:
        _merge_equipment(client, equipment_name)
        client.execute_cypher(
            """
            MATCH (e:Exercise {name: $exercise_name})
            MATCH (eq:Equipment {name: $equipment_name})
            MERGE (e)-[:USES]->(eq)
            MERGE (e)-[:REQUIRES {priority: 'required'}]->(eq)
            """,
            {"exercise_name": exercise_name, "equipment_name": equipment_name},
            readonly=False,
        )
    return len(equipment_names)


def _link_exercise_goals(client: Neo4jClient, exercise_name: str, goals: list[str]) -> int:
    for goal in goals:
        client.execute_cypher(
            """
            MATCH (e:Exercise {name: $exercise_name})
            MERGE (g:Goal {name: $goal})
            MERGE (e)-[:ACHIEVES {effectiveness: 0.8}]->(g)
            """,
            {"exercise_name": exercise_name, "goal": goal},
            readonly=False,
        )
    return len(goals)


def _import_exercise_errors(client: Neo4jClient, exercise_name: str, errors: list[dict[str, Any]]) -> int:
    count = 0
    for error in errors:
        correction = error.get("correction") or {}
        client.execute_cypher(
            """
            MATCH (e:Exercise {name: $exercise_name})
            MERGE (ep:ErrorPoint {code: $error_code})
            SET ep.name = $error_name,
                ep.description = $description,
                ep.reason = $reason,
                ep.risk_level = $risk_level
            MERGE (e)-[:HAS_ERROR]->(ep)
            WITH ep
            MERGE (c:Correction {code: $correction_code})
            SET c.title = $title,
                c.solution = $solution,
                c.drills = $drills,
                c.frequency = $frequency,
                c.safety_note = $safety_note
            MERGE (ep)-[:CORRECT_BY]->(c)
            """,
            {
                "exercise_name": exercise_name,
                "error_code": error["code"],
                "error_name": error["name"],
                "description": error.get("description") or "",
                "reason": error.get("reason") or "",
                "risk_level": error.get("risk_level") or "medium",
                "correction_code": correction.get("code") or f"correct_{error['code']}",
                "title": correction.get("title") or "",
                "solution": correction.get("solution") or "",
                "drills": correction.get("drills") or "",
                "frequency": correction.get("frequency") or "",
                "safety_note": correction.get("safety_note") or "",
            },
            readonly=False,
        )
        count += 2
    return count


def _link_first_exercise_error_to_record(client: Neo4jClient, record_id: str, exercise_name: str) -> int:
    rows = client.execute_cypher(
        """
        MATCH (:Exercise {name: $exercise_name})-[:HAS_ERROR]->(ep:ErrorPoint)
        OPTIONAL MATCH (ep)-[:CORRECT_BY]->(c:Correction)
        RETURN ep.code AS error_code, c.code AS correction_code
        LIMIT 1
        """,
        {"exercise_name": exercise_name},
        readonly=True,
    )
    if not rows:
        return 0

    row = rows[0]
    client.execute_cypher(
        """
        MATCH (r:TrainingRecord {record_id: $record_id})
        MATCH (ep:ErrorPoint {code: $error_code})
        MERGE (r)-[:OBSERVED_ERROR {confidence: 0.6, metric: 'score'}]->(ep)
        WITH r
        OPTIONAL MATCH (c:Correction {code: $correction_code})
        FOREACH (_ IN CASE WHEN c IS NULL THEN [] ELSE [1] END |
            MERGE (r)-[:RECOMMENDED_CORRECTION]->(c)
        )
        """,
        {
            "record_id": record_id,
            "error_code": row.get("error_code"),
            "correction_code": row.get("correction_code"),
        },
        readonly=False,
    )
    return 2 if row.get("correction_code") else 1


def _merge_equipment(client: Neo4jClient, name: str) -> int:
    equipment_id = _equipment_id(name)
    client.execute_cypher(
        """
        MERGE (eq:Equipment {equipment_id: $equipment_id})
        SET eq.name = $name,
            eq.category = coalesce(eq.category, $category),
            eq.is_smart = coalesce(eq.is_smart, false),
            eq.status = coalesce(eq.status, 'normal')
        """,
        {"equipment_id": equipment_id, "name": name, "category": _equipment_category(name)},
        readonly=False,
    )
    return equipment_id


def _equipment_id(name: str) -> int:
    return 100_000 + zlib.crc32(name.encode("utf-8")) % 900_000


def _equipment_category(name: str) -> str:
    if name in {"杠铃", "哑铃", "力量器械"}:
        return "力量"
    if name in {"瑜伽垫", "弹力带"}:
        return "辅助"
    if name in {"跑道"}:
        return "场地"
    return "基础"


def _split_names(value: str) -> list[str]:
    normalized = value.replace("，", ",").replace("、", ",").replace("；", ",")
    return [item.strip() for item in normalized.split(",") if item.strip()]


def _resolve_goals_from_text(value: str) -> list[str]:
    mapping = {
        "力量": "增肌",
        "增肌": "增肌",
        "有氧": "减脂",
        "减脂": "减脂",
        "康复": "康复",
        "柔韧": "柔韧性",
        "核心": "综合训练",
        "综合": "综合训练",
    }
    goals = {goal for key, goal in mapping.items() if key in value}
    return sorted(goals or {"综合训练"})


def _merge_stats(target: ImportStats, source: ImportStats) -> None:
    target.users += source.users
    target.exercises += source.exercises
    target.venues += source.venues
    target.equipment += source.equipment
    target.training_records += source.training_records
    target.knowledge_items += source.knowledge_items
    target.relationships += source.relationships
    target.errors.extend(source.errors)


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(description="Import fitness knowledge and business data into Neo4j")
    parser.add_argument("--full", action="store_true", help="Import schema, knowledge base, and business data")
    parser.add_argument("--knowledge", action="store_true", help="Import only the structured fitness knowledge base")
    parser.add_argument("--business", action="store_true", help="Import only existing business data")
    args = parser.parse_args()

    if args.full:
        print(import_all())
    elif args.knowledge:
        if not is_available():
            print("Neo4j is not available.")
        else:
            initialize_graph_schema()
            print({"knowledge_items": import_knowledge_base()})
    elif args.business:
        if not is_available():
            print("Neo4j is not available.")
        else:
            print(import_business_data())
    else:
        parser.print_help()
