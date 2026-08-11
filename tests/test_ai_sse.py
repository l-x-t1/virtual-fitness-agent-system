from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ai.coach import AICoach
from app.ai.memory import ConversationStore
from app.ai.sse import AIStreamOrchestrator, encode_sse
from app.controllers import ai as ai_controller
from app.dependencies.auth import get_current_user
from app.llm import LLMClient, LLMError
from app.observability.tracer import Tracer


class OfflineLLM(LLMClient):
    def chat(self, *args, **kwargs):
        raise LLMError("offline")

    def available(self):
        return [{"provider": "deepseek", "default_model": "fake", "configured": False}]


class StreamingOfflineLLM(OfflineLLM):
    def stream_chat(self, messages, provider=None, model=None):
        return iter(["中文", "流式回答"])


class FakeGraph:
    async def astream(self, state, stream_mode="updates"):
        assert stream_mode == "updates"
        yield {"planning_agent": {"task_plan": {"goal": "安全训练"}}}
        yield {"recommend_agent": {"recommendations": []}}
        yield {"report_agent": {"report": {"summary": "完成"}}}


def make_coach(llm=None):
    return AICoach(
        llm=llm or OfflineLLM(),
        memory=ConversationStore(db_path=":memory:"),
        tracer=Tracer(enabled=False),
    )


def user():
    return {
        "id": 7,
        "nickname": "测试用户",
        "fitness_level": "beginner",
        "injuries": "膝盖不适",
        "preference": "低冲击",
    }


def event_names(chunks):
    return [line.split(": ", 1)[1] for chunk in chunks for line in chunk.splitlines() if line.startswith("event: ")]


async def collect(orchestrator, coach, disconnected=None):
    session = coach.create_session(user()["id"], "SSE")
    data = {"session_id": session["id"], "message": "深蹲膝盖怎么保护", "provider": "deepseek", "model": None}
    return [chunk async for chunk in orchestrator.stream(user(), [], data, disconnected)]


def test_sse_event_order_chinese_json_and_done():
    import asyncio

    coach = make_coach()
    chunks = asyncio.run(collect(AIStreamOrchestrator(coach, graph=FakeGraph()), coach))
    names = event_names(chunks)
    assert names[0:4] == ["start", "planning", "memory", "retrieval"]
    assert "tool" in names
    assert names[-2:] == ["final", "done"]
    assert "混合知识库检索完成" in "".join(chunks)
    for chunk in chunks:
        data_lines = [line[6:] for line in chunk.splitlines() if line.startswith("data: ")]
        for line in data_lines:
            json.loads(line)


def test_streaming_model_emits_token_before_final():
    import asyncio

    coach = make_coach(StreamingOfflineLLM())
    chunks = asyncio.run(collect(AIStreamOrchestrator(coach, graph=FakeGraph()), coach))
    names = event_names(chunks)
    assert "token" in names
    assert names.index("token") < names.index("final") < names.index("done")
    assert "中文" in "".join(chunks)


def test_stream_exception_becomes_safe_error_and_done():
    import asyncio

    class BrokenCoach:
        tracer = Tracer(enabled=False)

        def prepare_chat(self, *args, **kwargs):
            raise RuntimeError("secret stack details")

    orchestrator = AIStreamOrchestrator(BrokenCoach(), graph=FakeGraph())
    data = {"session_id": "missing", "message": "你好"}
    chunks = asyncio.run(
        _collect_direct(orchestrator, user(), data)
    )
    names = event_names(chunks)
    assert names[-2:] == ["error", "done"]
    assert "secret stack details" not in "".join(chunks)


async def _collect_direct(orchestrator, current_user, data, disconnected=None):
    return [chunk async for chunk in orchestrator.stream(current_user, [], data, disconnected)]


def test_client_disconnect_stops_without_final():
    import asyncio

    coach = make_coach()
    calls = 0

    async def disconnected():
        nonlocal calls
        calls += 1
        return calls >= 2

    chunks = asyncio.run(collect(AIStreamOrchestrator(coach, graph=FakeGraph()), coach, disconnected))
    assert "final" not in event_names(chunks)
    assert calls >= 2


def test_langgraph_nodes_map_to_sse_stages():
    import asyncio

    coach = make_coach()
    chunks = asyncio.run(collect(AIStreamOrchestrator(coach, graph=FakeGraph()), coach))
    text = "".join(chunks)
    assert "planning_agent" in text
    assert "recommend_agent" in text
    assert "report_agent" in text


def test_sse_endpoint_content_type_and_original_chat_route(monkeypatch):
    class EndpointStream:
        async def stream(self, *args, **kwargs):
            yield encode_sse("start", {"message": "你好", "trace_id": "t-1"})
            yield encode_sse("done", {"message": "结束", "trace_id": "t-1"})

    monkeypatch.setattr(ai_controller, "stream_orchestrator", EndpointStream())
    monkeypatch.setattr(ai_controller, "recent_history", lambda user_id: [])
    app = FastAPI()
    app.include_router(ai_controller.router)
    app.dependency_overrides[get_current_user] = lambda: user()
    client = TestClient(app)
    response = client.post(
        "/api/ai/chat/stream",
        json={"session_id": "session", "message": "中文测试", "provider": "deepseek"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "中文" not in response.text  # endpoint stream controls its own progress text
    assert "你好" in response.text

    paths = app.openapi()["paths"]
    assert "/api/ai/chat" in paths
    assert "/api/ai/chat/stream" in paths


def test_original_non_stream_chat_shape_remains_compatible():
    coach = make_coach()
    session = coach.create_session(user()["id"], "普通对话")
    result = coach.chat(
        user(),
        [],
        {"session_id": session["id"], "message": "如何热身", "provider": "deepseek", "model": None},
    )
    assert {"session_id", "answer", "mode", "sources", "state", "memory"} <= result.keys()
    assert result["mode"] == "demo"
