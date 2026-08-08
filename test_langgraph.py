"""LangGraph 多智能体协作系统测试 — 模拟任务场景1与场景2。

运行方式：
    python test_langgraph.py
    # 或
    python -m pytest test_langgraph.py -v

说明：通过 FakeRecommendAgent 替换 recommend_exercises 工具来源，
使两个场景的输出确定、可断言，验证的是多智能体编排逻辑本身。
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

from app.ai.langgraph_agent import run_agent


class FakeRecommendAgent:
    """模拟人员1的 RecommendAgent 工具，按场景返回可控推荐。

    - recommend_with_tools: 若 question 含"上次评估建议"（重试场景），
      返回徒手/低冲击动作；否则返回首次推荐。
    - recommend: 确定性回退，返回首次推荐。
    """

    def __init__(self):
        self.graph = SimpleNamespace(exercises=[], venues=[])
        self._tool_context = {}

    def recommend_with_tools(self, user, exercise_name=None, question=None):
        question = question or ""
        if "上次评估建议" in question:
            recs = [
                {"name": "俯卧撑", "equipment": "徒手", "match_score": 85},
                {"name": "波比跳", "equipment": "徒手", "match_score": 80},
                {"name": "登山者", "equipment": "徒手", "match_score": 78},
            ]
        else:
            recs = self._first_pass(user, question)
        return {"exercises": recs, "recommendations": recs}

    def recommend(self, user):
        return {"exercises": self._first_pass(user, "")}

    @staticmethod
    def _first_pass(user, question):
        text = question or ""
        # 减脂+膝盖 → 低冲击（设施类）
        if "减脂" in text or "膝盖" in text or "低冲击" in text:
            return [
                {"name": "游泳", "equipment": "游泳馆", "match_score": 88},
                {"name": "椭圆机", "equipment": "椭圆机", "match_score": 85},
                {"name": "骑自行车", "equipment": "单车", "match_score": 82},
            ]
        # 练胸 → 首次给出需器械动作（触发器材缺失回退）
        return [
            {"name": "卧推", "equipment": "杠铃", "match_score": 86},
            {"name": "俯卧撑", "equipment": "徒手", "match_score": 84},
            {"name": "飞鸟", "equipment": "飞鸟机", "match_score": 80},
        ]


def _run(message: str, user_id: int = 1) -> dict:
    with patch("agents.RecommendAgent", FakeRecommendAgent):
        return asyncio.run(run_agent(message, user_id))


def test_scenario1_fat_loss_knee_injury():
    """场景1：我要减脂，膝盖不好 → 规划/推荐/评估(通过)/激励/报告"""
    result = _run("我要减脂，膝盖不好")

    # 规划：识别出减脂目标 + 膝盖保护限制
    assert result["task_plan"]["goal"] == "减脂"
    assert any("膝" in c for c in result["task_plan"].get("constraints", []))

    # 推荐：低冲击动作
    names = [r.get("name", "") for r in result["recommendations"]]
    assert names  # 非空

    # 评估：低冲击匹配膝盖 → 通过（score >= 70）
    assert result["evaluation"]["score"] >= 70
    assert result["evaluation"]["passed"] is True

    # 激励 + 报告
    assert result["motivation"]
    assert result["report"]["summary"]
    assert result["current_step"] == "done"


def test_scenario2_chest_no_equipment_retry():
    """场景2：帮我制定练胸计划 → 首次需器械不通过 → 回退重推徒手 → 通过"""
    result = _run("帮我制定练胸计划")

    # 规划：练胸 → 增肌目标
    assert result["task_plan"]["goal"] == "增肌"

    # 发生过一次重试（retry_count >= 1，说明评估未通过后回到推荐）
    assert result["retry_count"] >= 1

    # 评估最终通过
    assert result["evaluation"]["passed"] is True
    assert result["evaluation"]["score"] >= 70

    # 最终推荐应为徒手动作（重推后）
    names = [r.get("name", "") for r in result["recommendations"]]
    assert "卧推" not in names  # 杠铃动作已被替换
    assert "俯卧撑" in names or "波比跳" in names

    # 报告
    assert result["report"]["summary"]
    assert result["current_step"] == "done"


def test_error_path_state_is_safe():
    """任一节点异常时，run_agent 不抛出，返回友好错误报告。"""
    with patch("agents.RecommendAgent", side_effect=RuntimeError("boom")):
        result = asyncio.run(run_agent("随便练练", 1))
    # 走到 error_handler，输出友好报告而非崩溃
    assert result["report"]["summary"]
    assert result["current_step"] == "done"
    assert result["error"]


if __name__ == "__main__":
    import sys

    passed = 0
    for name, fn in [
        ("场景1：减脂+膝盖 → 评估通过", test_scenario1_fat_loss_knee_injury),
        ("场景2：练胸无器材 → 回退重推 → 通过", test_scenario2_chest_no_equipment_retry),
        ("异常路径 → 友好错误", test_error_path_state_is_safe),
    ]:
        try:
            fn()
            print(f"  [OK] {name}")
            passed += 1
        except AssertionError as exc:
            print(f"  [FAIL] {name}: {exc}")
    print(f"{passed}/3 passed")
    sys.exit(0 if passed == 3 else 1)
