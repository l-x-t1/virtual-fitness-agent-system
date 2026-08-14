"""端到端测试：规划→推荐→评估→激励→报告 完整链路（人员4任务6）。

运行：
    python test_e2e.py
    python -m pytest test_e2e.py -v

说明：
- 通过 FakeRecommendAgent 替换 RecommendAgent，使链路确定可断言。
- 各 Agent 持有独立 LLMClient（隔离验证）。
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

from app.ai.langgraph_agent import run_agent
from agents import AgentCoordinator


class FakeRecommendAgent:
    """模拟 RecommendAgent：首次返回需器械动作，重试返回徒手动作。"""

    def __init__(self):
        self.graph = SimpleNamespace(exercises=[], venues=[])
        self._tool_context = {}

    def recommend_with_tools(self, user, exercise_name=None, question=None):
        question = question or ""
        if "上次评估建议" in question:
            recs = [
                {"name": "俯卧撑", "equipment": "徒手", "match_score": 85},
                {"name": "波比跳", "equipment": "徒手", "match_score": 80},
            ]
        else:
            recs = self._first_pass(user, question)
        return {"exercises": recs, "recommendations": recs}

    def recommend(self, user):
        return {"exercises": self._first_pass(user, "")}

    @staticmethod
    def _first_pass(user, question):
        text = question or ""
        if "减脂" in text or "膝盖" in text or "低冲击" in text:
            return [
                {"name": "游泳", "equipment": "游泳馆", "match_score": 88},
                {"name": "椭圆机", "equipment": "椭圆机", "match_score": 85},
            ]
        return [
            {"name": "卧推", "equipment": "杠铃", "match_score": 86},
            {"name": "飞鸟", "equipment": "飞鸟机", "match_score": 80},
        ]


def _run(message: str, user_id: int = 1) -> dict:
    with patch("agents.RecommendAgent", FakeRecommendAgent):
        return asyncio.run(run_agent(message, user_id))


# ============================================================
# 测试1：完整链路（场景1 - 减脂+膝盖）
# ============================================================

def test_full_flow_scenario1_fat_loss():
    result = _run("我要减脂，膝盖不好")

    # 规划
    assert result["task_plan"]["goal"] == "减脂"
    assert any("膝" in c for c in result["task_plan"].get("constraints", []))

    # 推荐
    assert result["recommendations"]
    assert len(result["recommendations"]) >= 1

    # 评估
    assert "score" in result["evaluation"]
    assert result["evaluation"]["passed"] is True
    assert result["evaluation"]["score"] >= 70

    # 激励
    assert result["motivation"]

    # 报告
    assert result["report"]["summary"]
    assert result["report"]["plan"]

    # 结束
    assert result["current_step"] == "done"


# ============================================================
# 测试2：完整链路（场景2 - 练胸无器材 → 回退重推）
# ============================================================

def test_full_flow_scenario2_retry():
    result = _run("帮我制定练胸计划")

    assert result["task_plan"]["goal"] == "增肌"
    assert result["retry_count"] >= 1          # 发生过回退重推
    assert result["evaluation"]["passed"] is True

    names = [r.get("name", "") for r in result["recommendations"]]
    assert "卧推" not in names                 # 需杠铃的动作已被替换
    assert result["report"]["summary"]
    assert result["current_step"] == "done"


# ============================================================
# 测试3：通过 AgentCoordinator 入口
# ============================================================

def test_coordinator_run_workflow():
    with patch("agents.RecommendAgent", FakeRecommendAgent):
        coord = AgentCoordinator()
        result = asyncio.run(coord.run_workflow("我要减脂，膝盖不好", 1))

    assert result["task_plan"]["goal"] == "减脂"
    assert result["recommendations"]
    assert result["report"]["summary"]
    assert result["current_step"] == "done"


# ============================================================
# 测试4：Agent 隔离（不共享 LLM 实例）
# ============================================================

def test_agents_have_isolated_llm():
    coord = AgentCoordinator()
    # 不同 Agent 的 LLMClient 应是不同实例
    assert coord.profile.llm_client is not coord.recommendation.llm_client
    assert coord.recommendation.llm_client is not coord.report.llm_client
    # 每次 _make_llm() 也返回新实例
    from app.ai.langgraph_agent import _make_llm

    assert _make_llm() is not _make_llm()


if __name__ == "__main__":
    tests = [
        ("场景1 完整链路（减脂+膝盖）", test_full_flow_scenario1_fat_loss),
        ("场景2 完整链路（练胸回退重推）", test_full_flow_scenario2_retry),
        ("AgentCoordinator 入口", test_coordinator_run_workflow),
        ("Agent LLM 隔离", test_agents_have_isolated_llm),
    ]
    passed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  [OK] {name}")
            passed += 1
        except AssertionError as exc:
            print(f"  [FAIL] {name}: {exc}")
    print(f"{passed}/{len(tests)} passed")
    raise SystemExit(0 if passed == len(tests) else 1)
