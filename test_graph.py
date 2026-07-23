"""Smoke tests for the Neo4j knowledge graph module.

Usage:
    python test_graph.py

The script is intentionally safe for local development: if the optional Neo4j
Python package is missing or the database is offline, it reports the reason and
exits successfully. Once Neo4j is running, it verifies connection and runs a
small read query.
"""

from __future__ import annotations

from app.graph.cypher_query import (
    find_correction_plan,
    find_exercise_errors,
    find_related_exercises,
    find_user_training_history,
    search_training_knowledge,
)
from app.graph.data_import import load_knowledge_base
from app.core.config import settings
from app.graph.graph_schema import schema_summary
from app.graph.neo4j_client import Neo4jClient, Neo4jUnavailableError
from app.graphrag import GraphRAGChain, GraphRetriever


def test_schema_definition() -> None:
    summary = schema_summary()
    node_labels = {item["label"] for item in summary["nodes"]}
    relationship_types = {item["type"] for item in summary["relationships"]}

    required_nodes = {
        "User",
        "TrainingRecord",
        "Exercise",
        "BodyPart",
        "Muscle",
        "ErrorPoint",
        "Correction",
        "Equipment",
        "Goal",
        "Level",
    }
    required_relationships = {
        "HAS_RECORD",
        "CONTAINS",
        "TARGETS",
        "USES",
        "HAS_ERROR",
        "CORRECT_BY",
        "HAS_GOAL",
        "HAS_LEVEL",
    }

    assert required_nodes <= node_labels
    assert required_relationships <= relationship_types
    print(f"Schema definition OK: {len(node_labels)} nodes, {len(relationship_types)} relationships.")


def test_knowledge_base_definition() -> None:
    knowledge = load_knowledge_base()
    exercises = knowledge["exercises"]
    assert exercises

    for exercise in exercises:
        assert exercise["name"]
        assert exercise["standard_action"]
        assert exercise["errors"]
        for error in exercise["errors"]:
            assert error["code"]
            assert error["name"]
            assert error["reason"]
            assert error["correction"]["solution"]

    error_count = sum(len(exercise["errors"]) for exercise in exercises)
    print(f"Knowledge base OK: {len(exercises)} exercises, {error_count} error-correction chains.")


class FakeNeo4jClient:
    def __init__(self):
        self.calls = []

    def execute_cypher(self, query, params=None, readonly=True):
        self.calls.append({"query": query, "params": params or {}, "readonly": readonly})
        if "HAS_RECORD" in query:
            return [{"record_id": "session:1", "exercise": "深蹲", "error": "膝盖内扣"}]
        if "HAS_ERROR" in query and "CORRECT_BY" in query:
            return [{"exercise": "深蹲", "error": "膝盖内扣", "correction": "加强髋外展训练"}]
        if "related_exercises" in query:
            return []
        return [{"type": "Exercise", "name": "深蹲", "summary": "标准深蹲"}]


def test_cypher_query_api() -> None:
    client = FakeNeo4jClient()

    history = find_user_training_history(1, client=client)
    errors = find_exercise_errors("深蹲", client=client)
    plans = find_correction_plan(exercise_name="深蹲", error_name="膝盖内扣", client=client)
    related = find_related_exercises("深蹲", client=client)
    search = search_training_knowledge("膝盖", client=client)

    assert history["records"]
    assert errors["errors"]
    assert plans["plans"]
    assert "related_exercises" in related
    assert search["knowledge"]
    assert all(call["readonly"] is True for call in client.calls)
    assert client.calls[0]["params"]["user_id"] == 1
    assert client.calls[1]["params"]["exercise_name"] == "深蹲"
    assert client.calls[-1]["params"]["keyword"] == "膝盖"
    print(f"Cypher query API OK: {len(client.calls)} parameterized read queries.")


class FakeQueryService:
    def search_training_knowledge(self, query, limit=8):
        return {
            "query": query,
            "knowledge": [
                {
                    "type": "Exercise",
                    "name": "深蹲",
                    "summary": "膝盖跟随脚尖方向，躯干保持稳定。",
                    "metadata": {"category": "力量训练", "difficulty": 2},
                },
                {
                    "type": "ErrorPoint",
                    "name": "膝盖内扣",
                    "summary": "臀中肌和髋外旋控制不足。",
                    "metadata": {"code": "squat_knee_valgus", "risk_level": "high"},
                },
            ],
        }

    def find_exercise_errors(self, exercise_name, limit=8):
        return {
            "exercise": exercise_name,
            "errors": [
                {
                    "exercise": exercise_name,
                    "error": "膝盖内扣",
                    "reason": "臀中肌和髋外旋控制不足。",
                    "correction": "降低深蹲深度，使用弹力带提示膝盖外推。",
                    "drills": "弹力带侧向走、蚌式开合、箱式深蹲。",
                    "safety_note": "若膝关节刺痛或肿胀，应停止训练。",
                }
            ],
        }

    def find_related_exercises(self, exercise_name, limit=8):
        return {"exercise": exercise_name, "related_exercises": [{"exercise": "弓步蹲"}]}

    def find_correction_plan(self, exercise_name=None, error_code=None, error_name=None, limit=8):
        return {
            "plans": [
                {
                    "error": "膝盖内扣",
                    "solution": "加强髋外展与膝盖力线控制。",
                    "drills": "弹力带侧向走。",
                }
            ]
        }

    def find_user_training_history(self, user_id, limit=8):
        return {"user_id": user_id, "records": []}


def test_graphrag_chain() -> None:
    retriever = GraphRetriever(query_service=FakeQueryService())
    chain = GraphRAGChain(retriever=retriever, use_llm=False)
    result = chain.invoke("我的深蹲膝盖疼是什么原因？")

    assert result["knowledge"]
    assert result["relations"]
    assert "膝盖内扣" in result["context"]
    assert "纠正建议" in result["answer"]
    assert result["used_llm"] is False
    print("GraphRAG chain OK: retrieval context and fallback answer generated.")


def test_neo4j_connection() -> bool:
    client = Neo4jClient()
    print(f"Neo4j URI: {settings.neo4j_uri}")
    print(f"Neo4j database: {settings.neo4j_database}")

    if not client.verify_connectivity():
        print("Neo4j is not available. Start it before running graph import/query tests.")
        return False

    rows = client.execute_cypher("RETURN 1 AS ok", readonly=True)
    assert rows == [{"ok": 1}]
    print("Neo4j connection OK.")
    return True


def main() -> None:
    test_schema_definition()
    test_knowledge_base_definition()
    test_cypher_query_api()
    test_graphrag_chain()

    try:
        connected = test_neo4j_connection()
    except Neo4jUnavailableError as exc:
        print(f"Neo4j driver unavailable: {exc}")
        return

    if connected:
        print("Graph smoke test passed.")
    else:
        print("Graph smoke test skipped because Neo4j is offline.")


if __name__ == "__main__":
    main()
