"""多智能体协作系统的共享状态定义（AgentState）。

状态是节点之间唯一的通信渠道。路由、有限重试、GraphRAG 上下文和
降级原因均由 LangGraph 通过该状态管理。
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
      next_step:       兼容旧调用方的下一节点名称
      route:           conditional_edges 使用的显式路由值
      graph_context:   GraphRAG 只读检索结果或不可用状态
      retry_count:     当前重试次数
      max_retries:     最大重试次数
      error:           结构化错误信息
      failed_step:     最近失败的节点
      retryable:       最近错误是否允许重试
      fallback_reason: 进入降级流程的原因
      completed_steps: 已完成节点（追加式累积）
      trace_id:        可选可观测链路 ID
      session_id:      可选会话 ID
    """

    messages: Annotated[list[dict[str, Any]], operator.add]
    user_info: dict[str, Any]
    task_plan: dict[str, Any]
    recommendations: list[dict[str, Any]]
    evaluation: dict[str, Any]
    motivation: str
    report: dict[str, Any]
    graph_context: dict[str, Any]
    current_step: str
    next_step: str
    route: str
    retry_count: int
    max_retries: int
    error: dict[str, Any] | str
    failed_step: str
    retryable: bool
    fallback_reason: str
    completed_steps: Annotated[list[str], operator.add]
    trace_id: str
    session_id: str
