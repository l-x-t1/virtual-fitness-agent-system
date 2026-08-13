"""人员 3：状态流转、有限重试和公开入口兼容测试。"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import app.ai.langgraph_agent as workflow


def _initial(message: str, *, max_retries: int = 2) -> dict:
    return {
        "messages": [{"role": "user", "content": message}],
        "user_info": {"id": 7, "nickname": "测试用户"},
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
        "max_retries": max_retries,
        "error": {},
        "failed_step": "",
        "retryable": False,
        "fallback_reason": "",
        "completed_steps": [],
    }


def test_unknown_intent_reaches_safe_fallback_without_external_calls(monkeypatch):
    monkeypatch.setattr(workflow, "_plan_via_llm", lambda *_: None)
    result = asyncio.run(workflow.compiled_graph.ainvoke(_initial("你好呀")))
    assert result["current_step"] == "done"
    assert result["report"]["fallback"] is True
    assert result["fallback_reason"] == "unsupported_intent"
    assert "fallback_node" in result["completed_steps"]


def test_error_handler_retries_only_up_to_state_limit():
    retry = workflow.error_handler({
        "failed_step": "recommend_agent",
        "retryable": True,
        "retry_count": 0,
        "max_retries": 1,
    })
    assert retry["route"] == "retry_recommend_agent"
    assert retry["retry_count"] == 1

    exhausted = workflow.error_handler({
        "failed_step": "recommend_agent",
        "retryable": True,
        "retry_count": 1,
        "max_retries": 1,
    })
    assert exhausted["route"] == "fallback"
    assert exhausted["fallback_reason"] == "retry_exhausted"


def test_graph_node_failure_retries_then_falls_back(monkeypatch):
    monkeypatch.setattr(workflow, "_plan_via_llm", lambda *_: None)

    def failed_recommend(_state):
        return {
            "error": {"node": "recommend_agent", "code": "TEST_FAILURE"},
            "failed_step": "recommend_agent",
            "retryable": True,
            "route": "error",
            "current_step": "error_handler",
            "next_step": "error_handler",
        }

    monkeypatch.setattr(workflow, "recommend_agent", failed_recommend)
    graph = workflow.build_graph()
    result = asyncio.run(graph.ainvoke(_initial("帮我制定训练计划", max_retries=1)))
    assert result["current_step"] == "done"
    assert result["retry_count"] == 1
    assert result["fallback_reason"] == "retry_exhausted"
    assert result["report"]["fallback"] is True
    assert result["completed_steps"].count("error_handler") == 2


def test_astream_updates_remains_compatible(monkeypatch):
    monkeypatch.setattr(workflow, "_plan_via_llm", lambda *_: None)

    async def collect():
        return [
            update
            async for update in workflow.compiled_graph.astream(
                _initial("未知请求"), stream_mode="updates"
            )
        ]

    updates = asyncio.run(collect())
    assert updates
    assert "planning_agent" in updates[0]
    assert any("fallback_node" in update for update in updates)


def test_run_agent_signature_and_return_shape_remain_compatible(monkeypatch):
    monkeypatch.setattr(workflow, "_load_user_info", lambda _user_id: {"id": 9})
    monkeypatch.setattr(workflow, "_plan_via_llm", lambda *_: None)
    result = asyncio.run(workflow.run_agent("你好", 9))
    assert result["next_step"] == "done"
    assert result["report"]["fallback"] is True


def test_safe_step_exposes_structured_error_without_internal_message():
    def explode(_state):
        raise RuntimeError("token=private-value")

    update = workflow._safe_step("recommend_agent", explode)({})
    assert update["route"] == "error"
    assert update["error"]["node"] == "recommend_agent"
    assert update["error"]["code"] == "NODE_EXECUTION_FAILED"
    assert "private-value" not in str(update["error"])
