"""AgentCoordinator — 复用 LLMClient.bind_tools() 的多智能体协调层。

- 统一持有 5 个 Agent（画像/动作评估/推荐/激励/报告），各 Agent 内部持有
  独立的 LLMClient（见 app.agents.base.BaseAgent），互不共享实例与状态。
- 通过 LLMClient.bind_tools() 把 RecommendAgent 的工具绑定给 LLM，实现
  Function Calling 触发的工具调用推荐。
- 提供到人员3 LangGraph 工作流（run_agent）的入口。
"""

from __future__ import annotations

from typing import Any

from agents import GameAgent, MotionAgent, ProfileAgent, RecommendAgent, ReportAgent
from app.llm import LLMClient


class AgentCoordinator:
    """协调 5 个健身 Agent 的统一入口。"""

    def __init__(self, llm: LLMClient | None = None):
        self.llm = llm or LLMClient()
        self.profile = ProfileAgent()
        self.motion = MotionAgent()
        self.recommendation = RecommendAgent()
        self.game = GameAgent()
        self.report = ReportAgent()

    # ---- 工具绑定（复用 LLMClient.bind_tools） ----

    def recommend_tools(self) -> list[Any]:
        """推荐 Agent 暴露的工具：recommend_exercises / recommend_venues。"""
        return self.recommendation.tools()

    def bound_recommend_llm(self) -> LLMClient:
        """把推荐工具绑定到 LLMClient，返回带工具的客户端实例（Function Calling 用）。"""
        return self.llm.bind_tools(self.recommend_tools())

    def recommend_with_tools(
        self,
        user: dict[str, Any],
        exercise_name: str | None = None,
        question: str | None = None,
    ) -> dict[str, Any]:
        """通过 LLM 的 Function Calling 触发 recommend_exercises 工具完成推荐。"""
        return self.recommendation.recommend_with_tools(
            user, exercise_name=exercise_name, question=question
        )

    # ---- 完整多智能体工作流（人员3 的 LangGraph 编排） ----

    async def run_workflow(self, user_message: str, user_id: int | str) -> dict[str, Any]:
        """运行规划→推荐→评估→激励→报告 完整链路。"""
        from app.ai.langgraph_agent import run_agent

        return await run_agent(user_message, user_id)

    # ---- 单 Agent 快捷入口（保持与业务调用兼容） ----

    def recommend(self, user: dict[str, Any], exercise_name: str | None = None) -> dict[str, Any]:
        return self.recommendation.recommend(user, exercise_name)

    def evaluate(self, exercise_name: str, raw_score: int, pose_data=None):
        return self.motion.evaluate(exercise_name, raw_score, pose_data)

    def build_report(self, user_id: int):
        return self.report.build_report(user_id)

    def settle(self, repo, user: dict[str, Any], score: int, duration: int):
        return self.game.settle(repo, user, score, duration)
