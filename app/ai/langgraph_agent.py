"""多智能体协作系统（LangGraph 调度层）。

流程：
  用户输入 → planning_agent → recommend_agent → evaluate_agent
      ├─ 评估通过(score>=70) → motivate_agent → report_agent → 输出
      └─ 评估不通过 → 回到 recommend_agent（补充条件重试）
  任一节点异常 → error_handler → 返回友好错误信息

使用人员1（工具调用基础层）的 LLMClient.bind_tools 与 RecommendAgent 工具，
不改动其 llm_client.py / tools.py / agents.py。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from langgraph.graph import END, START, StateGraph

from app.ai.state import AgentState
from app.llm.client import LLMClient, LLMConfigurationError

logger = logging.getLogger(__name__)

MAX_RETRY = 2  # 评估不通过的最大重试次数

# 节点名集合（供路由判断用）
_NODES = {
    "planning_agent",
    "recommend_agent",
    "evaluate_agent",
    "motivate_agent",
    "report_agent",
    "error_handler",
}


# ============================================================
# 通用工具
# ============================================================

def _make_llm() -> LLMClient:
    return LLMClient()


def _parse_json_response(text: str) -> dict[str, Any]:
    """从 LLM 输出中提取 JSON 对象（容忍 markdown 围栏）。"""
    content = (text or "").strip()
    if content.startswith("```"):
        content = content.split("```")[1]
        if content.lstrip().startswith("json"):
            content = content.lstrip()[4:]
    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("LLM 输出中未找到 JSON 对象")
    return json.loads(content[start : end + 1])


def _safe_step(name: str, fn: Callable | None = None):
    """节点包装器：任一节点抛异常时返回错误状态，路由到 error_handler。

    同时支持 `@_safe_step("name")` 和 `_safe_step("name", fn)` 两种用法。
    """

    def decorator(func: Callable[[AgentState], dict[str, Any]]):
        def wrapped(state: AgentState) -> dict[str, Any]:
            try:
                return func(state)
            except Exception as exc:  # noqa: BLE001 - 顶层兜底
                logger.exception("%s failed", name)
                return {
                    "error": f"{name}: {exc}",
                    "current_step": "error_handler",
                    "next_step": "error_handler",
                }

        return wrapped

    if fn is not None:
        return decorator(fn)
    return decorator


def _load_user_info(user_id: int) -> dict[str, Any]:
    """从业务库加载用户画像（失败时返回空 dict）。"""
    try:
        from app.repositories import FitnessRepository, session_scope

        with session_scope() as session:
            repo = FitnessRepository(session)
            return repo.user_by_id(int(user_id)) or {}
    except Exception as exc:  # pragma: no cover - 数据库不可用时兜底
        logger.warning("load user failed: %s", exc)
        return {}


# ============================================================
# 节点1：规划 Agent
# ============================================================

def _infer_goal(message: str) -> str:
    text = message or ""
    if any(k in text for k in ("减脂", "减肥", "瘦", "有氧")):
        return "减脂"
    if any(k in text for k in ("增肌", "练胸", "练背", "力量", "肌肉")):
        return "增肌"
    if any(k in text for k in ("塑形", "线条", "雕刻")):
        return "塑形"
    if any(k in text for k in ("康复", "膝盖", "受伤", "恢复", "腰痛")):
        return "康复"
    return "综合训练"


_GOAL_SUBTASKS: dict[str, list[str]] = {
    "减脂": ["有氧训练", "低冲击动作", "热量缺口"],
    "增肌": ["力量训练", "大肌群动作", "渐进负荷"],
    "塑形": ["均衡训练", "核心强化", "柔韧性"],
    "康复": ["低冲击动作", "关节保护", "逐步恢复"],
    "综合训练": ["全身训练", "有氧+力量结合", "循序渐进"],
}


def _plan_via_llm(user_info: dict[str, Any], message: str) -> dict[str, Any] | None:
    try:
        client = _make_llm()
        prompt = (
            "你是健身规划智能体。根据用户信息和需求，规划训练子任务。"
            '只返回 JSON：{"goal": "目标", "subtasks": ["子任务1", "子任务2"], "constraints": ["限制1"]}。\n'
            f"用户信息：{json.dumps(user_info, ensure_ascii=False)}\n"
            f"用户需求：{message}\n"
        )
        raw = client.invoke(prompt)
        return _parse_json_response(raw)
    except Exception:  # noqa: BLE001 - LLM 不可用走关键词推断
        return None


def _extract_constraints(user_info: dict[str, Any], message: str) -> list[str]:
    """从用户画像 + 原始消息中提取训练限制条件。"""
    constraints: list[str] = []
    text = (message or "") + " " + (user_info.get("injuries") or "")
    if any(k in text for k in ("膝", "踝")):
        constraints.append("关节保护：膝/踝")
    if "腰" in text:
        constraints.append("关节保护：腰部")
    if any(k in text for k in ("无器材", "徒手", "家里", "没器械")):
        constraints.append("器材：徒手")
    # 用户画像明确的偏好/限制
    if user_info.get("preference"):
        constraints.append(f"偏好：{user_info['preference']}")
    return constraints


@_safe_step("planning_agent")
def planning_agent(state: AgentState) -> dict[str, Any]:
    messages = state.get("messages") or []
    user_message = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            user_message = m.get("content", "")
            break
    user_info = state.get("user_info") or {}

    plan = _plan_via_llm(user_info, user_message)
    if not plan:
        goal = _infer_goal(user_message)
        plan = {
            "goal": goal,
            "subtasks": _GOAL_SUBTASKS.get(goal, _GOAL_SUBTASKS["综合训练"]),
            "constraints": _extract_constraints(user_info, user_message),
        }

    return {
        "task_plan": plan,
        "current_step": "recommending",
        "next_step": "recommend_agent",
    }


# ============================================================
# 节点2：推荐 Agent（通过 Function Calling 触发 recommend_exercises 工具）
# ============================================================

def _build_recommend_question(plan: dict[str, Any], evaluation: dict[str, Any]) -> str:
    goal = plan.get("goal", "")
    subtasks = "、".join(plan.get("subtasks", []))
    constraints = "、".join(plan.get("constraints", [])) or "无特殊限制"
    note = ""
    if evaluation.get("suggestions"):
        note = "；上次评估建议：" + "、".join(evaluation["suggestions"][:3])
    return (
        f"用户目标：{goal}；子任务：{subtasks}；限制：{constraints}。"
        f"请调用 recommend_exercises 工具返回适合的动作候选。{note}"
    )


@_safe_step("recommend_agent")
def recommend_agent(state: AgentState) -> dict[str, Any]:
    user_info = state.get("user_info") or {}
    plan = state.get("task_plan") or {}
    evaluation = state.get("evaluation") or {}
    retry_count = state.get("retry_count") or 0

    from agents import RecommendAgent

    recommendations: list[dict[str, Any]] = []
    mode = "fallback"
    try:
        agent = RecommendAgent()
        result = agent.recommend_with_tools(
            user=user_info,
            question=_build_recommend_question(plan, evaluation),
        )
        recommendations = result.get("exercises") or result.get("recommendations") or []
        mode = "tool-call" if recommendations else "fallback"
    except Exception:  # noqa: BLE001 - LLM 不可用走确定性回退
        try:
            agent = RecommendAgent()
            result = agent.recommend(user_info)
            recommendations = result.get("exercises") or result.get("recommendations") or []
        except Exception as exc:  # pragma: no cover
            return {
                "error": f"recommend_agent: {exc}",
                "current_step": "error_handler",
                "next_step": "error_handler",
            }

    # 将推荐结果追加到消息历史
    msg = {
        "role": "assistant",
        "content": f"推荐了 {len(recommendations)} 个动作（{mode}）",
        "agent": "recommend_agent",
    }
    return {
        "recommendations": recommendations,
        "current_step": "evaluating",
        "next_step": "evaluate_agent",
        "retry_count": retry_count,
        "messages": [msg],
    }


# ============================================================
# 节点3：评估 Agent
# ============================================================

def _evaluate_via_llm(user_info: dict[str, Any], plan: dict[str, Any], recs: list[dict[str, Any]]) -> dict[str, Any] | None:
    try:
        client = _make_llm()
        prompt = (
            "你是健身评估智能体。评估推荐动作是否匹配用户目标与限制条件。"
            '只返回 JSON：{"score": 0-100, "feedback": "分析", "suggestions": ["改进1"]}。\n'
            f"用户信息：{json.dumps(user_info, ensure_ascii=False)}\n"
            f"计划：{json.dumps(plan, ensure_ascii=False)}\n"
            f"推荐：{json.dumps(recs, ensure_ascii=False)}\n"
        )
        raw = client.invoke(prompt)
        return _parse_json_response(raw)
    except (LLMConfigurationError, ValueError, Exception):  # noqa: BLE001
        return None


# 高风险动作 → 涉及的关节（用于伤病评估）
_HIGH_IMPACT: dict[str, list[str]] = {
    "深蹲": ["膝", "踝"],
    "开合跳": ["膝", "踝"],
    "弓步蹲": ["膝"],
    "节奏冲刺": ["膝", "踝"],
    "平板支撑": ["腰"],
}
# 视为"无需器材"的动作（弹力带等家用小器械可算徒手）
_BODYWEGHT_EQUIPMENT = {"", "徒手", "徒手训练", "弹力带", "瑜伽垫"}
# 需要健身房重型器械的关键词（徒手用户被推荐这类动作时判定为器材缺失）
_GYM_EQUIPMENT_KEYWORDS = ("杠铃", "哑铃", "器械", "飞鸟机", "卧推凳", "龙门架")


def _heuristic_evaluate(user_info: dict[str, Any], plan: dict[str, Any], recs: list[dict[str, Any]]) -> dict[str, Any]:
    """无 LLM 时的确定性评估：检查伤病限制、器材可用性。"""
    score = 70
    feedback_parts: list[str] = []
    suggestions: list[str] = []

    text = " ".join(plan.get("constraints", [])) + " " + (user_info.get("injuries") or "")
    has_equipment = bool(user_info.get("equipment"))

    for item in recs[:3]:
        name = item.get("name", "")
        equipment = (item.get("equipment") or "").strip()
        # 1) 伤病限制：高风险动作命中受伤关节
        risky = [part for part in _HIGH_IMPACT.get(name, []) if part in text]
        if risky:
            score -= 20
            suggestions.append(f"替换 {name} 为低冲击动作")
            feedback_parts.append(f"{name} 涉及{'/'.join(risky)}风险")
        # 2) 器材限制：徒手用户被推荐了需要健身房器械的动作
        if (
            not has_equipment
            and equipment not in _BODYWEGHT_EQUIPMENT
            and any(k in equipment for k in _GYM_EQUIPMENT_KEYWORDS)
        ):
            score -= 15
            suggestions.append(f"{name} 需要 {equipment}，改为徒手动作")
            feedback_parts.append(f"{name} 需要器材，用户无器材")

    score = max(0, min(100, score))
    feedback = "；".join(feedback_parts) or "推荐动作与用户目标及限制匹配"
    return {"score": score, "feedback": feedback, "suggestions": suggestions}


@_safe_step("evaluate_agent")
def evaluate_agent(state: AgentState) -> dict[str, Any]:
    user_info = state.get("user_info") or {}
    plan = state.get("task_plan") or {}
    recs = state.get("recommendations") or []
    retry_count = state.get("retry_count") or 0

    evaluation = _evaluate_via_llm(user_info, plan, recs)
    if not evaluation:
        evaluation = _heuristic_evaluate(user_info, plan, recs)
    evaluation["passed"] = float(evaluation.get("score", 0)) >= 70

    if evaluation["passed"] or retry_count >= MAX_RETRY:
        return {
            "evaluation": evaluation,
            "current_step": "motivating",
            "next_step": "motivate_agent",
            "retry_count": retry_count,
        }
    # 不通过：回到推荐节点重新推荐
    return {
        "evaluation": evaluation,
        "current_step": "recommending",
        "next_step": "recommend_agent",
        "retry_count": retry_count + 1,
    }


# ============================================================
# 节点4：激励 Agent
# ============================================================

def _motivate_via_llm(user_info: dict[str, Any], evaluation: dict[str, Any]) -> str | None:
    try:
        client = _make_llm()
        prompt = (
            "你是健身激励智能体。根据用户画像和评估结果，生成一句简短、个性化的鼓励语。\n"
            f"用户信息：{json.dumps(user_info, ensure_ascii=False)}\n"
            f"评估：{json.dumps(evaluation, ensure_ascii=False)}\n"
            "只返回一句话，不要 JSON。\n"
        )
        raw = client.invoke(prompt)
        text = (raw or "").strip()
        return text or None
    except (LLMConfigurationError, Exception):  # noqa: BLE001
        return None


@_safe_step("motivate_agent")
def motivate_agent(state: AgentState) -> dict[str, Any]:
    user_info = state.get("user_info") or {}
    evaluation = state.get("evaluation") or {}
    nickname = user_info.get("nickname") or user_info.get("username") or "朋友"

    motivation = _motivate_via_llm(user_info, evaluation)
    if not motivation:
        passed = evaluation.get("passed", True)
        motivation = (
            f"{nickname}，方案已经匹配你的目标，坚持按计划执行，你会看到变化！"
            if passed
            else f"{nickname}，别灰心，我们调整了方案让它更适合你，慢慢来，保持节奏！"
        )

    return {
        "motivation": motivation,
        "current_step": "reporting",
        "next_step": "report_agent",
    }


# ============================================================
# 节点5：报告 Agent
# ============================================================

def _report_via_llm(state_data: dict[str, Any]) -> dict[str, Any] | None:
    try:
        client = _make_llm()
        prompt = (
            "你是健身报告智能体。汇总所有结果，生成一份结构化训练方案报告。"
            '只返回 JSON：{"summary": "总结", "plan": ["执行建议"], "expected": "预期效果", "motivation": "鼓励语"}。\n'
            f"数据：{json.dumps(state_data, ensure_ascii=False)}\n"
        )
        raw = client.invoke(prompt)
        return _parse_json_response(raw)
    except (LLMConfigurationError, ValueError, Exception):  # noqa: BLE001
        return None


@_safe_step("report_agent")
def report_agent(state: AgentState) -> dict[str, Any]:
    plan = state.get("task_plan") or {}
    recs = state.get("recommendations") or []
    evaluation = state.get("evaluation") or {}
    motivation = state.get("motivation") or ""

    state_snapshot = {
        "task_plan": plan,
        "recommendations": recs,
        "evaluation": evaluation,
        "motivation": motivation,
    }
    report = _report_via_llm(state_snapshot)
    if not report:
        goal = plan.get("goal", "综合训练")
        names = [item.get("name", "") for item in recs[:5]]
        report = {
            "summary": f"已为你的「{goal}」目标生成训练方案，共推荐 {len(names)} 个动作。",
            "plan": [f"动作：{name}" for name in names] or ["请补充画像后重新推荐"],
            "expected": "坚持执行并记录表现，2-4 周可观察到改善。",
            "motivation": motivation,
        }

    return {
        "report": report,
        "current_step": "done",
        "next_step": "__end__",
    }


# ============================================================
# 错误处理节点
# ============================================================

@_safe_step("error_handler")
def error_handler(state: AgentState) -> dict[str, Any]:
    # 保留 state.error 供调用方排查；error_handler 的出边是直达 END，不会循环
    return {
        "report": {
            "summary": "处理过程中出现问题，请稍后重试或补充更完整的个人画像。",
            "plan": [],
            "expected": "",
            "motivation": "别担心，我们可以重新来过。",
        },
        "current_step": "done",
        "next_step": "__end__",
    }


# ============================================================
# 构建流程图
# ============================================================

def _route(state: AgentState) -> str:
    if state.get("error"):
        return "error_handler"
    nxt = state.get("next_step") or "error_handler"
    return nxt if nxt in _NODES or nxt == "__end__" else "error_handler"


def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("planning_agent", planning_agent)
    graph.add_node("recommend_agent", recommend_agent)
    graph.add_node("evaluate_agent", evaluate_agent)
    graph.add_node("motivate_agent", motivate_agent)
    graph.add_node("report_agent", report_agent)
    graph.add_node("error_handler", error_handler)

    graph.add_edge(START, "planning_agent")

    path_map = {
        "planning_agent": "planning_agent",
        "recommend_agent": "recommend_agent",
        "evaluate_agent": "evaluate_agent",
        "motivate_agent": "motivate_agent",
        "report_agent": "report_agent",
        "error_handler": "error_handler",
        "__end__": END,
    }
    # 除 error_handler 外的节点都走条件路由（error → error_handler，否则按 next_step）
    for node_name in _NODES - {"error_handler"}:
        graph.add_conditional_edges(node_name, _route, path_map)
    # error_handler 处理后直达结束，避免 error 残留导致循环
    graph.add_edge("error_handler", END)

    compiled = graph.compile()
    compiled.name = "fitness_multi_agent"  # 可选：命名编译图
    return compiled


compiled_graph = build_graph()


# ============================================================
# 运行入口
# ============================================================

async def run_agent(user_message: str, user_id: int | str) -> dict[str, Any]:
    """运行多智能体协作，返回最终报告及中间状态。

    Args:
        user_message: 用户原始消息，如"我要减脂，膝盖不好"
        user_id: 用户ID，用于加载画像
    """
    user_info = _load_user_info(user_id)

    initial: AgentState = {
        "messages": [{"role": "user", "content": user_message}],
        "user_info": user_info,
        "task_plan": {},
        "recommendations": [],
        "evaluation": {},
        "motivation": "",
        "report": {},
        "current_step": "planning",
        "next_step": "planning_agent",
        "retry_count": 0,
        "error": "",
    }

    result = await compiled_graph.ainvoke(initial)

    # 返回结果中剔除内部路由字段，保持对外干净
    output = dict(result)
    output["next_step"] = "done"
    return output
