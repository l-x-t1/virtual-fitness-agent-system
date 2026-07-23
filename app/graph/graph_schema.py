"""Canonical schema for the fitness knowledge graph.

This module defines the professional fitness graph used by GraphRAG. It is
separate from the legacy recommendation schema so existing features can keep
working while the richer action-error-correction knowledge chain is added.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.graph.neo4j_client import Neo4jClient, Neo4jUnavailableError


@dataclass(frozen=True)
class PropertyDefinition:
    name: str
    type: str
    required: bool = False
    description: str = ""


@dataclass(frozen=True)
class NodeDefinition:
    label: str
    key: str
    description: str
    properties: tuple[PropertyDefinition, ...]


@dataclass(frozen=True)
class RelationshipDefinition:
    type: str
    start_label: str
    end_label: str
    description: str
    properties: tuple[PropertyDefinition, ...] = ()


NODE_DEFINITIONS: tuple[NodeDefinition, ...] = (
    NodeDefinition(
        label="User",
        key="user_id",
        description="System user profile synchronized from the business database.",
        properties=(
            PropertyDefinition("user_id", "Integer", True, "Business user id."),
            PropertyDefinition("nickname", "String", False, "Display name."),
            PropertyDefinition("age", "Integer", False, "User age."),
            PropertyDefinition("fitness_level", "String", False, "beginner/intermediate/advanced."),
            PropertyDefinition("injuries", "String", False, "Known injury history."),
            PropertyDefinition("preference", "String", False, "Training preference text."),
            PropertyDefinition("location", "String", False, "Common training location."),
            PropertyDefinition("points", "Integer", False, "Gamified points."),
            PropertyDefinition("level", "Integer", False, "Gamified level."),
        ),
    ),
    NodeDefinition(
        label="TrainingRecord",
        key="record_id",
        description="One completed or observed training session.",
        properties=(
            PropertyDefinition("record_id", "String", True, "Stable graph id, for example session:12."),
            PropertyDefinition("session_id", "Integer", False, "Business training session id."),
            PropertyDefinition("user_id", "Integer", False, "Business user id."),
            PropertyDefinition("exercise_name", "String", False, "Recorded exercise name."),
            PropertyDefinition("score", "Integer", False, "Motion evaluation score."),
            PropertyDefinition("duration", "Integer", False, "Training duration in seconds."),
            PropertyDefinition("feedback", "String", False, "Generated feedback."),
            PropertyDefinition("created_at", "DateTime", False, "Record creation time."),
        ),
    ),
    NodeDefinition(
        label="Exercise",
        key="name",
        description="Fitness action or movement pattern.",
        properties=(
            PropertyDefinition("exercise_id", "Integer", False, "Business exercise id."),
            PropertyDefinition("name", "String", True, "Exercise name, for example squat."),
            PropertyDefinition("category", "String", False, "Strength/cardio/core/mobility."),
            PropertyDefinition("difficulty", "Integer", False, "Difficulty from 1 to 5."),
            PropertyDefinition("target", "String", False, "Primary target text."),
            PropertyDefinition("standard_action", "String", False, "Human-readable standard action description."),
            PropertyDefinition("standard_json", "String", False, "Structured standard metrics."),
            PropertyDefinition("precautions", "String", False, "Safety notes."),
        ),
    ),
    NodeDefinition(
        label="BodyPart",
        key="name",
        description="Body region involved in training or pain feedback.",
        properties=(
            PropertyDefinition("name", "String", True, "Body part name."),
            PropertyDefinition("alias", "String", False, "Alternative names."),
            PropertyDefinition("description", "String", False, "Body part description."),
        ),
    ),
    NodeDefinition(
        label="Muscle",
        key="name",
        description="Muscle or muscle group targeted by exercises.",
        properties=(
            PropertyDefinition("name", "String", True, "Muscle name."),
            PropertyDefinition("body_part", "String", False, "Related body part."),
            PropertyDefinition("function", "String", False, "Primary biomechanical function."),
            PropertyDefinition("alias", "String", False, "Alternative names."),
        ),
    ),
    NodeDefinition(
        label="ErrorPoint",
        key="code",
        description="Common form error, pain clue, or risk point in an exercise.",
        properties=(
            PropertyDefinition("code", "String", True, "Stable error code."),
            PropertyDefinition("name", "String", True, "Error name, for example knee valgus."),
            PropertyDefinition("description", "String", False, "Observable symptoms."),
            PropertyDefinition("reason", "String", False, "Likely cause."),
            PropertyDefinition("risk_level", "String", False, "low/medium/high."),
        ),
    ),
    NodeDefinition(
        label="Correction",
        key="code",
        description="Standard correction plan for an error point.",
        properties=(
            PropertyDefinition("code", "String", True, "Stable correction code."),
            PropertyDefinition("title", "String", True, "Correction plan title."),
            PropertyDefinition("solution", "String", False, "Correction instructions."),
            PropertyDefinition("drills", "String", False, "Auxiliary drills."),
            PropertyDefinition("frequency", "String", False, "Suggested practice frequency."),
            PropertyDefinition("safety_note", "String", False, "Safety boundary."),
        ),
    ),
    NodeDefinition(
        label="Equipment",
        key="equipment_id",
        description="Training equipment concept or synchronized equipment item.",
        properties=(
            PropertyDefinition("equipment_id", "Integer", True, "Business or seeded equipment id."),
            PropertyDefinition("name", "String", True, "Equipment name."),
            PropertyDefinition("category", "String", False, "Equipment category."),
            PropertyDefinition("is_smart", "Boolean", False, "Whether it is smart equipment."),
            PropertyDefinition("status", "String", False, "normal/maintenance/offline."),
            PropertyDefinition("location", "String", False, "Equipment location."),
            PropertyDefinition("venue_id", "Integer", False, "Owning venue id when applicable."),
        ),
    ),
    NodeDefinition(
        label="Goal",
        key="name",
        description="Training goal such as hypertrophy, fat loss, or rehab.",
        properties=(
            PropertyDefinition("name", "String", True, "Goal name."),
            PropertyDefinition("description", "String", False, "Goal description."),
            PropertyDefinition("priority", "Integer", False, "Default priority."),
        ),
    ),
    NodeDefinition(
        label="Level",
        key="name",
        description="Training ability level.",
        properties=(
            PropertyDefinition("name", "String", True, "beginner/intermediate/advanced."),
            PropertyDefinition("rank", "Integer", False, "Comparable level rank."),
            PropertyDefinition("description", "String", False, "Level description."),
        ),
    ),
)


RELATIONSHIP_DEFINITIONS: tuple[RelationshipDefinition, ...] = (
    RelationshipDefinition("HAS_RECORD", "User", "TrainingRecord", "User owns a training record."),
    RelationshipDefinition("CONTAINS", "TrainingRecord", "Exercise", "Record contains an exercise."),
    RelationshipDefinition(
        "TARGETS",
        "Exercise",
        "Muscle",
        "Exercise trains a muscle.",
        (PropertyDefinition("weight", "Float", False, "Targeting strength from 0 to 1."),),
    ),
    RelationshipDefinition("LOCATED_IN", "Muscle", "BodyPart", "Muscle belongs to a body part."),
    RelationshipDefinition("USES", "Exercise", "Equipment", "Exercise uses equipment."),
    RelationshipDefinition("HAS_ERROR", "Exercise", "ErrorPoint", "Exercise has a common error point."),
    RelationshipDefinition("CORRECT_BY", "ErrorPoint", "Correction", "Error point can be corrected by a plan."),
    RelationshipDefinition("HAS_GOAL", "User", "Goal", "User has a training goal."),
    RelationshipDefinition("HAS_LEVEL", "User", "Level", "User has a training level."),
    RelationshipDefinition(
        "OBSERVED_ERROR",
        "TrainingRecord",
        "ErrorPoint",
        "A training record observed an error point.",
        (
            PropertyDefinition("confidence", "Float", False, "Detection confidence from pose data."),
            PropertyDefinition("metric", "String", False, "Related motion metric."),
        ),
    ),
    RelationshipDefinition(
        "RECOMMENDED_CORRECTION",
        "TrainingRecord",
        "Correction",
        "A correction recommended for a specific record.",
    ),
)


# Existing recommendation graph compatibility. These labels/relationships are
# already used by app.graph.queries and should remain valid.
COMPATIBILITY_RELATIONSHIPS: tuple[RelationshipDefinition, ...] = (
    RelationshipDefinition("REQUIRES", "Exercise", "Equipment", "Legacy alias for Exercise uses Equipment."),
    RelationshipDefinition("ACHIEVES", "Exercise", "Goal", "Legacy exercise-to-goal relation."),
    RelationshipDefinition("PREFERS", "User", "Goal", "Legacy alias for User has Goal."),
    RelationshipDefinition("COMPLETED", "User", "Exercise", "Legacy direct completion relation."),
    RelationshipDefinition("HAS_EQUIPMENT", "Venue", "Equipment", "Venue owns equipment."),
    RelationshipDefinition("SUITABLE_FOR", "Venue", "Exercise", "Venue is suitable for an exercise."),
    RelationshipDefinition("TRAINED_AT", "User", "Venue", "User trained at a venue."),
)


CONSTRAINTS: tuple[str, ...] = (
    "CREATE CONSTRAINT kg_user_id IF NOT EXISTS FOR (u:User) REQUIRE u.user_id IS UNIQUE",
    "CREATE CONSTRAINT kg_training_record_id IF NOT EXISTS FOR (r:TrainingRecord) REQUIRE r.record_id IS UNIQUE",
    "CREATE CONSTRAINT kg_exercise_name IF NOT EXISTS FOR (e:Exercise) REQUIRE e.name IS UNIQUE",
    "CREATE CONSTRAINT kg_body_part_name IF NOT EXISTS FOR (b:BodyPart) REQUIRE b.name IS UNIQUE",
    "CREATE CONSTRAINT kg_muscle_name IF NOT EXISTS FOR (m:Muscle) REQUIRE m.name IS UNIQUE",
    "CREATE CONSTRAINT kg_error_point_code IF NOT EXISTS FOR (ep:ErrorPoint) REQUIRE ep.code IS UNIQUE",
    "CREATE CONSTRAINT kg_correction_code IF NOT EXISTS FOR (c:Correction) REQUIRE c.code IS UNIQUE",
    "CREATE CONSTRAINT kg_equipment_id IF NOT EXISTS FOR (eq:Equipment) REQUIRE eq.equipment_id IS UNIQUE",
    "CREATE CONSTRAINT kg_goal_name IF NOT EXISTS FOR (g:Goal) REQUIRE g.name IS UNIQUE",
    "CREATE CONSTRAINT kg_level_name IF NOT EXISTS FOR (l:Level) REQUIRE l.name IS UNIQUE",
    "CREATE CONSTRAINT kg_venue_id IF NOT EXISTS FOR (v:Venue) REQUIRE v.venue_id IS UNIQUE",
    "CREATE CONSTRAINT kg_muscle_group_name IF NOT EXISTS FOR (mg:MuscleGroup) REQUIRE mg.name IS UNIQUE",
)


INDEXES: tuple[str, ...] = (
    "CREATE INDEX kg_user_fitness_level IF NOT EXISTS FOR (u:User) ON (u.fitness_level)",
    "CREATE INDEX kg_user_location IF NOT EXISTS FOR (u:User) ON (u.location)",
    "CREATE INDEX kg_training_record_user IF NOT EXISTS FOR (r:TrainingRecord) ON (r.user_id)",
    "CREATE INDEX kg_training_record_created IF NOT EXISTS FOR (r:TrainingRecord) ON (r.created_at)",
    "CREATE INDEX kg_training_record_exercise IF NOT EXISTS FOR (r:TrainingRecord) ON (r.exercise_name)",
    "CREATE INDEX kg_exercise_category IF NOT EXISTS FOR (e:Exercise) ON (e.category)",
    "CREATE INDEX kg_exercise_difficulty IF NOT EXISTS FOR (e:Exercise) ON (e.difficulty)",
    "CREATE INDEX kg_error_point_name IF NOT EXISTS FOR (ep:ErrorPoint) ON (ep.name)",
    "CREATE INDEX kg_error_point_risk IF NOT EXISTS FOR (ep:ErrorPoint) ON (ep.risk_level)",
    "CREATE INDEX kg_equipment_name IF NOT EXISTS FOR (eq:Equipment) ON (eq.name)",
    "CREATE INDEX kg_equipment_category IF NOT EXISTS FOR (eq:Equipment) ON (eq.category)",
    "CREATE INDEX kg_venue_location IF NOT EXISTS FOR (v:Venue) ON (v.location)",
)


REFERENCE_DATA_CYPHER: tuple[tuple[str, dict[str, Any]], ...] = (
    (
        "UNWIND $items AS item MERGE (b:BodyPart {name: item.name}) "
        "SET b.alias = item.alias, b.description = item.description",
        {
            "items": [
                {"name": "膝关节", "alias": "膝盖", "description": "下肢动作中常见疼痛和稳定性观察部位。"},
                {"name": "髋部", "alias": "骨盆,髋关节", "description": "深蹲、弓步蹲和硬拉的关键发力区域。"},
                {"name": "核心", "alias": "躯干", "description": "维持身体稳定和力线控制的中枢区域。"},
                {"name": "肩部", "alias": "肩关节", "description": "上肢推拉和支撑动作的重要稳定部位。"},
            ]
        },
    ),
    (
        "UNWIND $items AS item MERGE (m:Muscle {name: item.name}) "
        "SET m.body_part = item.body_part, m.function = item.function, m.alias = item.alias",
        {
            "items": [
                {"name": "股四头肌", "body_part": "膝关节", "function": "伸膝和下肢支撑", "alias": "大腿前侧"},
                {"name": "臀大肌", "body_part": "髋部", "function": "伸髋和髋稳定", "alias": "臀部"},
                {"name": "臀中肌", "body_part": "髋部", "function": "髋外展和膝盖力线控制", "alias": "髋外展肌"},
                {"name": "腘绳肌", "body_part": "髋部", "function": "屈膝和伸髋辅助", "alias": "大腿后侧"},
                {"name": "腹横肌", "body_part": "核心", "function": "核心抗伸展和腹压稳定", "alias": "深层核心"},
                {"name": "三角肌", "body_part": "肩部", "function": "肩关节外展和稳定", "alias": "肩肌"},
            ]
        },
    ),
    (
        "UNWIND $items AS item MERGE (g:Goal {name: item.name}) "
        "SET g.description = item.description, g.priority = item.priority",
        {
            "items": [
                {"name": "增肌", "description": "提高肌肉体积和力量基础。", "priority": 1},
                {"name": "减脂", "description": "提高能量消耗并改善心肺能力。", "priority": 2},
                {"name": "康复", "description": "降低疼痛风险并恢复动作控制。", "priority": 3},
                {"name": "柔韧性", "description": "改善关节活动度和肌肉延展性。", "priority": 4},
                {"name": "综合训练", "description": "兼顾力量、耐力、协调和稳定。", "priority": 5},
            ]
        },
    ),
    (
        "UNWIND $items AS item MERGE (l:Level {name: item.name}) "
        "SET l.rank = item.rank, l.description = item.description",
        {
            "items": [
                {"name": "beginner", "rank": 1, "description": "新手，优先学习动作模式和安全控制。"},
                {"name": "intermediate", "rank": 2, "description": "进阶，具备基础训练经验，可增加负荷和复杂度。"},
                {"name": "advanced", "rank": 3, "description": "高级，可进行高强度或专项训练。"},
            ]
        },
    ),
)


def initialize_graph_schema(client: Neo4jClient | None = None, include_reference_data: bool = True) -> dict[str, Any]:
    """Apply constraints, indexes, and optional reference data to Neo4j."""
    client = client or Neo4jClient()
    result: dict[str, Any] = {"constraints": 0, "indexes": 0, "reference_data": 0, "errors": []}

    try:
        for statement in CONSTRAINTS:
            client.execute_cypher(statement, readonly=False)
            result["constraints"] += 1
        for statement in INDEXES:
            client.execute_cypher(statement, readonly=False)
            result["indexes"] += 1
        if include_reference_data:
            for statement, params in REFERENCE_DATA_CYPHER:
                client.execute_cypher(statement, params, readonly=False)
                result["reference_data"] += 1
    except Neo4jUnavailableError as exc:
        result["errors"].append(str(exc))
    except Exception as exc:  # The caller should see the failed statement count.
        result["errors"].append(str(exc))
    finally:
        client.close()

    return result


def schema_summary() -> dict[str, Any]:
    """Return a serializable schema overview for tests, docs, and API responses."""
    return {
        "nodes": [
            {
                "label": node.label,
                "key": node.key,
                "description": node.description,
                "properties": [property_def.__dict__ for property_def in node.properties],
            }
            for node in NODE_DEFINITIONS
        ],
        "relationships": [
            {
                "type": rel.type,
                "start_label": rel.start_label,
                "end_label": rel.end_label,
                "description": rel.description,
                "properties": [property_def.__dict__ for property_def in rel.properties],
            }
            for rel in RELATIONSHIP_DEFINITIONS
        ],
        "compatibility_relationships": [
            {
                "type": rel.type,
                "start_label": rel.start_label,
                "end_label": rel.end_label,
                "description": rel.description,
            }
            for rel in COMPATIBILITY_RELATIONSHIPS
        ],
    }
