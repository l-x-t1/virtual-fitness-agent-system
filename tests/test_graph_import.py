"""图谱导入模块测试：新增的 RISK / SUITABLE_FOR 关系创建逻辑"""

import pytest

from app.graph.data_import import (
    EXERCISE_RISK_LEVELS,
    _link_exercise_risk,
    _link_venue_suitable_for,
)
from app.graph.queries import RECOMMEND_WITH_RISK_FILTER, resolve_risky_body_parts


class FakeNeo4jClient:
    """记录执行过的 Cypher，返回可控结果"""

    def __init__(self):
        self.calls = []

    def execute_cypher(self, query, params=None, readonly=True):
        self.calls.append({"query": query, "params": params or {}, "readonly": readonly})
        if "SUITABLE_FOR" in query and "MATCH (v:Venue)" in query:
            return [{"linked": 3}]
        return []

    def close(self):
        pass


def test_exercise_risk_levels_defined():
    """高风险动作应定义膝关节等高危部位级别"""
    assert EXERCISE_RISK_LEVELS["深蹲"]["膝关节"] == "high"
    assert EXERCISE_RISK_LEVELS["平板支撑"]["核心"] == "low"


def test_link_exercise_risk_creates_risky_relationship():
    client = FakeNeo4jClient()
    _link_exercise_risk(client, "深蹲", ["膝关节", "髋部"], category="力量训练")

    assert len(client.calls) == 2
    for call in client.calls:
        assert "RISK" in call["query"]
        assert call["readonly"] is False
    # 深蹲对膝关节风险为 high
    knee_call = next(c for c in client.calls if c["params"]["body_part"] == "膝关节")
    assert knee_call["params"]["level"] == "high"


def test_link_venue_suitable_for_returns_count():
    client = FakeNeo4jClient()
    count = _link_venue_suitable_for(client)
    assert count == 3
    assert "SUITABLE_FOR" in client.calls[0]["query"]


def test_resolve_risky_body_parts():
    assert resolve_risky_body_parts("膝关节不适") == ["膝关节"]
    assert resolve_risky_body_parts("腰部受伤") == ["腰部"]
    assert resolve_risky_body_parts("无伤病史") == []
    assert resolve_risky_body_parts(None) == []


def test_risk_filter_query_uses_risky_body_parts_param():
    assert "$risky_body_parts" in RECOMMEND_WITH_RISK_FILTER
    assert "RISK" in RECOMMEND_WITH_RISK_FILTER
    assert "$limit" in RECOMMEND_WITH_RISK_FILTER
