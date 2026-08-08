"""多智能体协作系统的共享状态定义（AgentState）。

该状态由 LangGraph 在 5 个节点（规划/推荐/评估/激励/报告）之间传递，
所有节点共享同一份状态，各自更新自己负责的字段。
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class AgentState(TypedDict, total=False):
    """多智能体协作共享状态。

    字段说明：
      messages:        对话消息列表（所有 Agent 共享，追加式累积）
      user_info:       用户画像信息（年龄 / 目标 / 偏好 / 限制等）
      task_plan:       任务规划结果（子任务列表 / 执行顺序）
      recommendations: 推荐结果（动作名称 / 级别 / 器材 / 原因）
      evaluation:      评估结果（动作分析 / 改进建议 / 评分）
      motivation:      激励内容（字符串）
      report:          最终报告（总结 / 数据 / 下一步建议）
      current_step:    当前执行步骤（planning/recommending/evaluating/motivating/reporting）
      next_step:       下一步骤（用于分支判断）
      retry_count:     评估不通过时的重试次数（内部字段，防止死循环）
      error:           错误信息（失败时回退用）
    """

    messages: Annotated[list[dict[str, Any]], operator.add]
    user_info: dict[str, Any]
    task_plan: dict[str, Any]
    recommendations: list[dict[str, Any]]
    evaluation: dict[str, Any]
    motivation: str
    report: dict[str, Any]
    current_step: str
    next_step: str
    retry_count: int
    error: str
