"""Parameterized Cypher query API for the fitness knowledge graph."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.graph.neo4j_client import Neo4jClient, Neo4jUnavailableError


DEFAULT_LIMIT = 10
MAX_LIMIT = 50


@dataclass
class CypherQueryService:
    """Read-only query facade for GraphRAG and Agent integration."""

    client: Neo4jClient | None = None

    def __post_init__(self) -> None:
        if self.client is None:
            self.client = Neo4jClient()

    def find_user_training_history(self, user_id: int, limit: int = DEFAULT_LIMIT) -> dict[str, Any]:
        """Return recent training records, observed errors, and corrections for a user."""
        params = {"user_id": int(user_id), "limit": _safe_limit(limit)}
        rows = self._read(
            """
            MATCH (u:User {user_id: $user_id})
            OPTIONAL MATCH (u)-[:HAS_RECORD]->(r:TrainingRecord)
            OPTIONAL MATCH (r)-[:CONTAINS]->(e:Exercise)
            OPTIONAL MATCH (r)-[:OBSERVED_ERROR]->(ep:ErrorPoint)
            OPTIONAL MATCH (ep)-[:CORRECT_BY]->(c:Correction)
            RETURN u.user_id AS user_id,
                   u.nickname AS user,
                   r.record_id AS record_id,
                   r.session_id AS session_id,
                   r.score AS score,
                   r.duration AS duration,
                   r.feedback AS feedback,
                   r.created_at AS created_at,
                   e.name AS exercise,
                   ep.code AS error_code,
                   ep.name AS error,
                   ep.reason AS reason,
                   c.code AS correction_code,
                   c.title AS correction_title,
                   c.solution AS correction
            ORDER BY r.created_at DESC
            LIMIT $limit
            """,
            params,
        )
        return {
            "user_id": int(user_id),
            "records": [_without_none(row) for row in rows if row.get("record_id")],
        }

    def find_exercise_errors(self, exercise_name: str, limit: int = DEFAULT_LIMIT) -> dict[str, Any]:
        """Return common errors and correction plans for an exercise."""
        params = {"exercise_name": _required_text(exercise_name, "exercise_name"), "limit": _safe_limit(limit)}
        rows = self._read(
            """
            MATCH (e:Exercise {name: $exercise_name})-[:HAS_ERROR]->(ep:ErrorPoint)
            OPTIONAL MATCH (ep)-[:CORRECT_BY]->(c:Correction)
            RETURN e.name AS exercise,
                   ep.code AS error_code,
                   ep.name AS error,
                   ep.description AS description,
                   ep.reason AS reason,
                   ep.risk_level AS risk_level,
                   c.code AS correction_code,
                   c.title AS correction_title,
                   c.solution AS correction,
                   c.drills AS drills,
                   c.frequency AS frequency,
                   c.safety_note AS safety_note
            ORDER BY ep.risk_level DESC, ep.name
            LIMIT $limit
            """,
            params,
        )
        return {"exercise": exercise_name, "errors": [_without_none(row) for row in rows]}

    def find_correction_plan(
        self,
        exercise_name: str | None = None,
        error_code: str | None = None,
        error_name: str | None = None,
        limit: int = DEFAULT_LIMIT,
    ) -> dict[str, Any]:
        """Find correction plans by exercise, error code, or error name."""
        if not any([exercise_name, error_code, error_name]):
            raise ValueError("At least one of exercise_name, error_code, or error_name is required.")

        params = {
            "exercise_name": _optional_text(exercise_name),
            "error_code": _optional_text(error_code),
            "error_name": _optional_text(error_name),
            "limit": _safe_limit(limit),
        }
        rows = self._read(
            """
            MATCH (ep:ErrorPoint)-[:CORRECT_BY]->(c:Correction)
            OPTIONAL MATCH (e:Exercise)-[:HAS_ERROR]->(ep)
            WHERE ($exercise_name IS NULL OR e.name = $exercise_name)
              AND ($error_code IS NULL OR ep.code = $error_code)
              AND ($error_name IS NULL OR ep.name CONTAINS $error_name)
            RETURN e.name AS exercise,
                   ep.code AS error_code,
                   ep.name AS error,
                   ep.description AS description,
                   ep.reason AS reason,
                   ep.risk_level AS risk_level,
                   c.code AS correction_code,
                   c.title AS correction_title,
                   c.solution AS solution,
                   c.drills AS drills,
                   c.frequency AS frequency,
                   c.safety_note AS safety_note
            ORDER BY ep.risk_level DESC, e.name
            LIMIT $limit
            """,
            params,
        )
        return {
            "exercise": exercise_name,
            "error_code": error_code,
            "error_name": error_name,
            "plans": [_without_none(row) for row in rows],
        }

    def find_related_exercises(self, exercise_name: str, limit: int = DEFAULT_LIMIT) -> dict[str, Any]:
        """Find exercises related by muscles, goals, body parts, or common error types."""
        params = {"exercise_name": _required_text(exercise_name, "exercise_name"), "limit": _safe_limit(limit)}
        rows = self._read(
            """
            MATCH (base:Exercise {name: $exercise_name})
            OPTIONAL MATCH (base)-[:TARGETS]->(m:Muscle)<-[:TARGETS]-(by_muscle:Exercise)
            OPTIONAL MATCH (base)-[:ACHIEVES]->(g:Goal)<-[:ACHIEVES]-(by_goal:Exercise)
            OPTIONAL MATCH (base)-[:INVOLVES]->(b:BodyPart)<-[:INVOLVES]-(by_body:Exercise)
            OPTIONAL MATCH (base)-[:HAS_ERROR]->(ep:ErrorPoint)<-[:HAS_ERROR]-(by_error:Exercise)
            WITH base,
                 COLLECT(DISTINCT by_muscle) +
                 COLLECT(DISTINCT by_goal) +
                 COLLECT(DISTINCT by_body) +
                 COLLECT(DISTINCT by_error) AS candidates
            UNWIND candidates AS e
            WITH base, e
            WHERE e IS NOT NULL AND e.name <> base.name
            OPTIONAL MATCH (e)-[:TARGETS]->(m:Muscle)
            OPTIONAL MATCH (e)-[:ACHIEVES]->(g:Goal)
            OPTIONAL MATCH (e)-[:HAS_ERROR]->(ep:ErrorPoint)
            RETURN e.name AS exercise,
                   e.category AS category,
                   e.difficulty AS difficulty,
                   e.target AS target,
                   COLLECT(DISTINCT m.name) AS muscles,
                   COLLECT(DISTINCT g.name) AS goals,
                   COLLECT(DISTINCT ep.name) AS common_errors,
                   COUNT(DISTINCT m) + COUNT(DISTINCT g) + COUNT(DISTINCT ep) AS relation_score
            ORDER BY relation_score DESC, e.difficulty ASC
            LIMIT $limit
            """,
            params,
        )
        return {"exercise": exercise_name, "related_exercises": [_without_none(row) for row in rows]}

    def search_training_knowledge(self, query: str, limit: int = DEFAULT_LIMIT) -> dict[str, Any]:
        """Search exercises, errors, corrections, muscles, goals, and body parts by keyword."""
        keyword = _required_text(query, "query")
        params = {"keyword": keyword.lower(), "limit": _safe_limit(limit)}
        rows = self._read(
            """
            CALL {
              WITH $keyword AS keyword
              MATCH (e:Exercise)
              WHERE toLower(e.name) CONTAINS keyword
                 OR toLower(coalesce(e.category, '')) CONTAINS keyword
                 OR toLower(coalesce(e.standard_action, '')) CONTAINS keyword
                 OR toLower(coalesce(e.precautions, '')) CONTAINS keyword
              RETURN 'Exercise' AS type, e.name AS name,
                     coalesce(e.standard_action, e.target, '') AS summary,
                     {category: e.category, difficulty: e.difficulty} AS metadata
              UNION
              WITH $keyword AS keyword
              MATCH (ep:ErrorPoint)
              WHERE toLower(ep.name) CONTAINS keyword
                 OR toLower(coalesce(ep.description, '')) CONTAINS keyword
                 OR toLower(coalesce(ep.reason, '')) CONTAINS keyword
              RETURN 'ErrorPoint' AS type, ep.name AS name,
                     coalesce(ep.reason, ep.description, '') AS summary,
                     {code: ep.code, risk_level: ep.risk_level} AS metadata
              UNION
              WITH $keyword AS keyword
              MATCH (c:Correction)
              WHERE toLower(c.title) CONTAINS keyword
                 OR toLower(coalesce(c.solution, '')) CONTAINS keyword
                 OR toLower(coalesce(c.drills, '')) CONTAINS keyword
              RETURN 'Correction' AS type, c.title AS name,
                     coalesce(c.solution, '') AS summary,
                     {code: c.code, frequency: c.frequency} AS metadata
              UNION
              WITH $keyword AS keyword
              MATCH (m:Muscle)
              WHERE toLower(m.name) CONTAINS keyword
                 OR toLower(coalesce(m.function, '')) CONTAINS keyword
                 OR toLower(coalesce(m.alias, '')) CONTAINS keyword
              RETURN 'Muscle' AS type, m.name AS name,
                     coalesce(m.function, '') AS summary,
                     {body_part: m.body_part} AS metadata
              UNION
              WITH $keyword AS keyword
              MATCH (g:Goal)
              WHERE toLower(g.name) CONTAINS keyword
                 OR toLower(coalesce(g.description, '')) CONTAINS keyword
                 OR toLower(coalesce(g.recommendation, '')) CONTAINS keyword
              RETURN 'Goal' AS type, g.name AS name,
                     coalesce(g.description, g.recommendation, '') AS summary,
                     {priority: g.priority} AS metadata
            }
            RETURN type, name, summary, metadata
            LIMIT $limit
            """,
            params,
        )
        return {"query": query, "knowledge": [_without_none(row) for row in rows]}

    def find_risky_exercises(
        self, user_id: int, injuries: str | None = None, limit: int = DEFAULT_LIMIT
    ) -> dict[str, Any]:
        """根据用户伤病史，找出对其受伤部位有 RISK 关系的动作及风险级别。"""
        risky_parts = _resolve_body_parts(injuries)
        params = {"user_id": int(user_id), "risky_body_parts": risky_parts, "limit": _safe_limit(limit)}
        rows = self._read(
            """
            MATCH (u:User {user_id: $user_id})
            MATCH (b:BodyPart) WHERE b.name IN $risky_body_parts
            MATCH (e:Exercise)-[r:RISK]->(b)
            RETURN e.name AS exercise, b.name AS body_part, r.level AS risk_level,
                   e.category AS category, e.difficulty AS difficulty,
                   coalesce(e.precautions, '') AS precautions
            ORDER BY CASE r.level WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END
            LIMIT $limit
            """,
            params,
        )
        return {
            "user_id": int(user_id),
            "risky_body_parts": risky_parts,
            "risky_exercises": [_without_none(row) for row in rows],
        }

    def find_body_part_exercises(self, body_part: str, limit: int = DEFAULT_LIMIT) -> dict[str, Any]:
        """查询涉及指定身体部位的动作及其风险提示。"""
        params = {"body_part": _required_text(body_part, "body_part"), "limit": _safe_limit(limit)}
        rows = self._read(
            """
            MATCH (b:BodyPart {name: $body_part})
            MATCH (e:Exercise)-[:INVOLVES]->(b)
            OPTIONAL MATCH (e)-[r:RISK]->(b)
            RETURN e.name AS exercise, b.name AS body_part, r.level AS risk_level,
                   e.category AS category, e.difficulty AS difficulty,
                   coalesce(e.precautions, '') AS precautions
            ORDER BY CASE r.level WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END
            LIMIT $limit
            """,
            params,
        )
        return {
            "body_part": body_part,
            "exercises": [_without_none(row) for row in rows],
        }

    def _read(self, query: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            return self.client.execute_cypher(query, params, readonly=True) if self.client else []
        except Neo4jUnavailableError:
            return []
        except Exception:
            return []


def find_user_training_history(
    user_id: int,
    limit: int = DEFAULT_LIMIT,
    client: Neo4jClient | None = None,
) -> dict[str, Any]:
    return CypherQueryService(client).find_user_training_history(user_id, limit)


def find_exercise_errors(
    exercise_name: str,
    limit: int = DEFAULT_LIMIT,
    client: Neo4jClient | None = None,
) -> dict[str, Any]:
    return CypherQueryService(client).find_exercise_errors(exercise_name, limit)


def find_correction_plan(
    exercise_name: str | None = None,
    error_code: str | None = None,
    error_name: str | None = None,
    limit: int = DEFAULT_LIMIT,
    client: Neo4jClient | None = None,
) -> dict[str, Any]:
    return CypherQueryService(client).find_correction_plan(exercise_name, error_code, error_name, limit)


def find_related_exercises(
    exercise_name: str,
    limit: int = DEFAULT_LIMIT,
    client: Neo4jClient | None = None,
) -> dict[str, Any]:
    return CypherQueryService(client).find_related_exercises(exercise_name, limit)


def search_training_knowledge(
    query: str,
    limit: int = DEFAULT_LIMIT,
    client: Neo4jClient | None = None,
) -> dict[str, Any]:
    return CypherQueryService(client).search_training_knowledge(query, limit)


def find_risky_exercises(
    user_id: int,
    injuries: str | None = None,
    limit: int = DEFAULT_LIMIT,
    client: Neo4jClient | None = None,
) -> dict[str, Any]:
    return CypherQueryService(client).find_risky_exercises(user_id, injuries, limit)


def find_body_part_exercises(
    body_part: str,
    limit: int = DEFAULT_LIMIT,
    client: Neo4jClient | None = None,
) -> dict[str, Any]:
    return CypherQueryService(client).find_body_part_exercises(body_part, limit)


def _safe_limit(limit: int) -> int:
    return min(max(int(limit), 1), MAX_LIMIT)


# 伤病关键词 → 身体部位（与 app.graph.queries.INJURY_TO_BODY_PART 保持一致）
_INJURY_TO_BODY_PART: dict[str, str] = {
    "膝": "膝关节",
    "腰": "腰部",
    "肩": "肩部",
    "肘": "肘部",
    "踝": "踝部",
    "腕": "腕部",
    "髋": "髋部",
    "颈": "颈部",
    "背": "背部",
}


def _resolve_body_parts(injuries: str | None) -> list[str]:
    if not injuries:
        return []
    return [part for key, part in _INJURY_TO_BODY_PART.items() if key in injuries]


def _required_text(value: str, field_name: str) -> str:
    value = (value or "").strip()
    if not value:
        raise ValueError(f"{field_name} is required.")
    return value


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _without_none(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value is not None}
