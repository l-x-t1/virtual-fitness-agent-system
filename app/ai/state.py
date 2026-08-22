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
      control_route:   分类/槽位控制流路由（slot_validation/planning/clarification/fallback）
      intent:          轻量分类得到的细分意图
      sub_intent:      业务子意图
      intent_confidence: 分类置信度
      candidate_intents: 低置信或歧义时的候选意图
      missing_slots:   当前 intent 仍缺失的关键槽位
      awaiting_clarification: 是否正在等待用户回答追问
      clarification_count: 已追问轮数
      graph_context:   GraphRAG 只读检索结果或不可用状态
      tool_results:    环境、姿态或动作库工具的结构化执行结果
      retry_count:     当前重试次数
      max_retries:     最大重试次数
      error:           结构化错误信息
      failed_step:     最近失败的节点
      retryable:       最近错误是否允许重试
      fallback_reason: 进入降级流程的原因
      completed_steps: 已完成节点（追加式累积）
      trace_id:        可选可观测链路 ID
      session_id:      可选会话 ID
      slot_state:      当前会话完整槽位上下文
      slots_delta:     当前轮新增或变化的槽位
      slot_status:     complete/clarify/fallback
      slot_message:    追问或槽位处理提示
      slot_errors:     槽位校验错误列表
    """

    messages: Annotated[list[dict[str, Any]], operator.add]
    user_info: dict[str, Any]
    task_plan: dict[str, Any]
    recommendations: list[dict[str, Any]]
    evaluation: dict[str, Any]
    motivation: str
    report: dict[str, Any]
    graph_context: dict[str, Any]
    tool_results: list[dict[str, Any]]
    current_step: str
    next_step: str
    route: str
    control_route: str
    intent: str
    sub_intent: str
    intent_confidence: float
    candidate_intents: list[str]
    intent_reason: str
    missing_slots: list[str]
    awaiting_clarification: bool
    clarification_count: int
    conversation_context: dict[str, Any]
    retry_count: int
    max_retries: int
    error: dict[str, Any] | str
    failed_step: str
    retryable: bool
    fallback_reason: str
    completed_steps: Annotated[list[str], operator.add]
    trace_id: str
    session_id: str
    slot_state: dict[str, Any]
    slots_delta: dict[str, Any]
    slot_status: str
    slot_message: str
    slot_errors: list[str]
