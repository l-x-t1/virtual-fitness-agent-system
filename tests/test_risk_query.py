"""风险感知查询测试：CypherQueryService 新方法与风险解析"""

import pytest

from app.graph.cypher_query import (
    CypherQueryService,
    find_body_part_exercises,
    find_risky_exercises,
)
from app.graph.queries import (
    RECOMMEND_BY_BODY_PART,
    RECOMMEND_WITH_RISK_FILTER,
    resolve_risky_body_parts,
)


class FakeNeo4jClient:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def execute_cypher(self, query, params=None, readonly=True):
        self.calls.append({"query": query, "params": params or {}, "readonly": readonly})
        return self.rows


def test_find_risky_exercises():
    client = FakeNeo4jClient([
        {"exercise": "深蹲", "body_part": "膝关节", "risk_level": "high", "category": "力量训练", "difficulty": 2},
    ])
    result = find_risky_exercises(1, injuries="膝关节不适", client=client)

    assert result["risky_body_parts"] == ["膝关节"]
    assert result["risky_exercises"][0]["exercise"] == "深蹲"
    assert result["risky_exercises"][0]["risk_level"] == "high"
    assert client.calls[0]["readonly"] is True
    assert client.calls[0]["params"]["risky_body_parts"] == ["膝关节"]


def test_find_risky_exercises_without_injuries():
    client = FakeNeo4jClient([])
    result = find_risky_exercises(1, injuries=None, client=client)
    assert result["risky_body_parts"] == []
    assert result["risky_exercises"] == []


def test_find_body_part_exercises():
    client = FakeNeo4jClient([
        {"exercise": "深蹲", "body_part": "膝关节", "risk_level": "high", "category": "力量训练", "difficulty": 2},
    ])
    result = find_body_part_exercises("膝关节", client=client)

    assert result["body_part"] == "膝关节"
    assert len(result["exercises"]) == 1
    assert result["exercises"][0]["exercise"] == "深蹲"


def test_find_body_part_exercises_requires_name():
    client = FakeNeo4jClient([])
    with pytest.raises(ValueError):
        CypherQueryService(client).find_body_part_exercises("")


def test_risk_filter_query_imports():
    assert "RISK" in RECOMMEND_WITH_RISK_FILTER
    assert "BodyPart" in RECOMMEND_BY_BODY_PART
    assert "INVOLVES" in RECOMMEND_BY_BODY_PART


def test_resolve_risky_body_parts_multiple():
    assert resolve_risky_body_parts("膝盖和腰部都有问题") == ["膝关节", "腰部"]
