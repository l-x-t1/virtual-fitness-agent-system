"""人员 3：LangGraph 路由与状态定义专项测试。"""

from __future__ import annotations

import ast
import inspect

import app.ai.langgraph_agent as workflow
from app.ai.state import AgentState


def _state(message: str) -> AgentState:
    return {
        "messages": [{"role": "user", "content": message}],
        "user_info": {},
        "task_plan": {},
        "recommendations": [],
        "evaluation": {},
        "motivation": "",
        "report": {},
        "graph_context": {},
        "current_step": "planning",
        "next_step": "planning_agent",
        "route": "planning",
        "retry_count": 0,
        "max_retries": 2,
        "error": {},
        "completed_steps": [],
    }


def test_graph_compiles_with_start_end_and_conditional_edges():
    graph = workflow.build_graph().get_graph()
    assert "__start__" in graph.nodes
    assert "__end__" in graph.nodes
    assert any(edge.source == "__start__" and edge.target == "planning_agent" for edge in graph.edges)
    assert any(edge.conditional for edge in graph.edges)
    assert any(
        edge.conditional and edge.source == "planning_agent" and edge.target == "recommend_agent"
        for edge in graph.edges
    )


def test_full_flow_route_function_was_removed():
    assert not hasattr(workflow, "_route")
    source = inspect.getsource(workflow)
    assert "add_conditional_edges" in source


def test_planning_routes_supported_intents(monkeypatch):
    monkeypatch.setattr(workflow, "_plan_via_llm", lambda *_: None)
    cases = {
        "帮我制定减脂训练计划": "recommend",
        "请评估我的深蹲姿势": "evaluate",
        "最近没动力，请鼓励我": "motivate",
        "生成本周训练报告": "report",
        "深蹲膝盖疼怎么办": "graphrag",
        "今天天气真不错": "fallback",
    }
    for message, expected in cases.items():
        update = workflow.planning_agent(_state(message))
        assert update["route"] == expected
        assert workflow.planning_router(update) == expected


def test_condition_functions_only_read_state_and_return_routes():
    routers = (
        workflow.planning_router,
        workflow.graph_router,
        workflow.recommend_router,
        workflow.evaluate_router,
        workflow.motivate_router,
        workflow.report_router,
        workflow.retry_router,
    )
    business_names = {
        "planning_agent", "graphrag_node", "recommend_agent", "evaluate_agent",
        "motivate_agent", "report_agent", "error_handler", "fallback_node",
    }
    for router in routers:
        tree = ast.parse(inspect.getsource(router))
        called = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert called.isdisjoint(business_names)


def test_business_nodes_do_not_call_each_other_directly():
    nodes = (
        workflow.planning_agent,
        workflow.graphrag_node,
        workflow.recommend_agent,
        workflow.evaluate_agent,
        workflow.motivate_agent,
        workflow.report_agent,
        workflow.error_handler,
        workflow.fallback_node,
    )
    business_names = {node.__name__ for node in nodes}
    for node in nodes:
        tree = ast.parse(inspect.getsource(node))
        called = {
            child.func.id
            for child in ast.walk(tree)
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Name)
        }
        assert called.isdisjoint(business_names - {node.__name__})


def test_state_has_required_fields_and_no_secrets():
    fields = set(AgentState.__annotations__)
    required = {
        "messages", "user_info", "task_plan", "current_step", "route",
        "recommendations", "evaluation", "motivation", "report", "graph_context",
        "retry_count", "max_retries", "error", "fallback_reason",
        "completed_steps", "trace_id", "session_id",
    }
    assert required <= fields
    forbidden_fragments = ("api_key", "apikey", "jwt", "cookie", "password", "secret")
    assert not any(fragment in field.lower() for field in fields for fragment in forbidden_fragments)
