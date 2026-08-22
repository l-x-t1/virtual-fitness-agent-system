from __future__ import annotations

import asyncio
import inspect
import json
import time
from collections.abc import AsyncIterator, Callable
from typing import Any

from app.ai.state import AgentState
from app.observability.redaction import redact


def encode_sse(event: str, data: dict[str, Any]) -> str:
    payload = json.dumps(redact(data), ensure_ascii=False, separators=(",", ":"), default=str)
    return f"event: {event}\ndata: {payload}\n\n"


class AIStreamOrchestrator:
    """SSE adapter around existing Memory, Hybrid RAG, and compiled LangGraph."""

    NODE_EVENTS = {
        "planning_agent": "planning",
        "recommend_agent": "tool",
        "evaluate_agent": "tool",
        "motivate_agent": "tool",
        "report_agent": "tool",
        "error_handler": "error",
    }

    def __init__(self, coach: Any, graph: Any | None = None):
        self.coach = coach
        self._graph = graph

    async def stream(
        self,
        user: dict[str, Any],
        history: list[dict[str, Any]],
        data: dict[str, Any],
        is_disconnected: Callable[[], Any] | None = None,
    ) -> AsyncIterator[str]:
        trace = self.coach.tracer.start_trace(
            "ai_chat_stream",
            session_id=str(data.get("session_id") or ""),
            user_id=user.get("id"),
            metadata={
                "agent": "AICoach",
                "provider": data.get("provider"),
                "model": data.get("model"),
                "user_input": data.get("message"),
            },
        )
        trace_id = trace.trace_id
        prepared = None
        try:
            if await self._disconnected(is_disconnected):
                trace.event("sse.disconnected", {"stage": "start"})
                trace.finish({"status": "disconnected"})
                return
            yield encode_sse("start", {"message": "流式对话已开始", "trace_id": trace_id})
            yield encode_sse("planning", {"message": "正在规划处理流程", "trace_id": trace_id})
            yield encode_sse("memory", {"message": "正在读取会话与长期记忆", "trace_id": trace_id})

            prepared = await asyncio.to_thread(self.coach.prepare_chat, user, history, data, trace)
            retrieval = prepared["retrieval"]
            yield encode_sse(
                "retrieval",
                {
                    "message": "混合知识库检索完成",
                    "trace_id": trace_id,
                    "counts": retrieval["retrieval_counts"],
                    "sources": len(retrieval["evidence"]),
                    "rewrite_mode": retrieval["rewrite"].mode,
                    "rerank_mode": retrieval["rerank_mode"],
                },
            )

            async for event in self._langgraph_events(prepared, trace_id, trace):
                if await self._disconnected(is_disconnected):
                    trace.event("sse.disconnected", {"stage": "langgraph"})
                    trace.finish({"status": "disconnected"})
                    return
                yield event

            if await self._disconnected(is_disconnected):
                trace.event("sse.disconnected", {"stage": "generation"})
                trace.finish({"status": "disconnected"})
                return

            result = None
            stream_chat = getattr(self.coach.llm, "stream_chat", None)
            if callable(stream_chat) and prepared["retrieval"]["evidence"]:
                try:
                    answer = ""
                    chunk_count = 0
                    stream_started = time.perf_counter()
                    first_token_latency_ms = None
                    messages = self.coach.rag.answer_messages(
                        prepared["question"], prepared["retrieval"]
                    )
                    chunks = stream_chat(messages, data.get("provider"), data.get("model"))
                    if inspect.isawaitable(chunks):
                        chunks = await chunks
                    if hasattr(chunks, "__aiter__"):
                        async for chunk in chunks:
                            if await self._disconnected(is_disconnected):
                                trace.event("sse.disconnected", {"stage": "token"})
                                trace.finish({"status": "disconnected"})
                                return
                            text = str(chunk or "")
                            if text:
                                chunk_count += 1
                                if first_token_latency_ms is None:
                                    first_token_latency_ms = (time.perf_counter() - stream_started) * 1000
                                answer += text
                                yield encode_sse("token", {"text": text, "trace_id": trace_id})
                    else:
                        for chunk in chunks:
                            if await self._disconnected(is_disconnected):
                                trace.event("sse.disconnected", {"stage": "token"})
                                trace.finish({"status": "disconnected"})
                                return
                            text = str(chunk or "")
                            if text:
                                chunk_count += 1
                                if first_token_latency_ms is None:
                                    first_token_latency_ms = (time.perf_counter() - stream_started) * 1000
                                answer += text
                                yield encode_sse("token", {"text": text, "trace_id": trace_id})
                    if answer:
                        trace.event(
                            "llm.stream",
                            {
                                "provider": data.get("provider"),
                                "model": data.get("model"),
                                "chunk_count": chunk_count,
                                "output_tokens": max(1, len(answer) // 4),
                                "latency_ms": round((time.perf_counter() - stream_started) * 1000, 3),
                                "first_token_latency_ms": round(first_token_latency_ms or 0.0, 3),
                            },
                        )
                        result = await asyncio.to_thread(
                            self.coach.complete_chat,
                            prepared,
                            data,
                            answer_override=answer,
                            mode_override="online",
                        )
                except Exception:
                    trace.event("sse.token_fallback", {"reason": "streaming_model_failed"})

            if result is None:
                result = await asyncio.to_thread(self.coach.complete_chat, prepared, data)
            if await self._disconnected(is_disconnected):
                trace.event("sse.disconnected", {"stage": "final"})
                return
            yield encode_sse(
                "final",
                {
                    "message": "回答生成完成",
                    "trace_id": trace_id,
                    "result": result,
                },
            )
            yield encode_sse("done", {"message": "流式响应结束", "trace_id": trace_id})
        except asyncio.CancelledError:
            trace.event("sse.disconnected", {"stage": "cancelled"})
            trace.finish({"status": "disconnected"})
            return
        except Exception as exc:
            trace.event("sse.error", {"error": type(exc).__name__}, level="error")
            yield encode_sse(
                "error",
                {
                    "message": "处理请求时发生错误，请稍后重试。",
                    "trace_id": trace_id,
                    "error_code": "AI_STREAM_ERROR",
                },
            )
            yield encode_sse("done", {"message": "流式响应结束", "trace_id": trace_id})
            trace.finish(error=exc)

    async def _langgraph_events(
        self,
        prepared: dict[str, Any],
        trace_id: str,
        trace: Any | None = None,
    ) -> AsyncIterator[str]:
        try:
            graph = self._graph or self._load_graph()
            initial: AgentState = {
                "messages": [{"role": "user", "content": prepared["question"]}],
                "user_info": {**prepared["user"], **prepared["profile"]},
                "task_plan": {},
                "recommendations": [],
                "evaluation": {},
                "motivation": "",
                "report": {},
                "current_step": "planning",
                "next_step": "planning_agent",
                "route": "planning",
                "control_route": "classification",
                "retry_count": 0,
                "error": "",
                "session_id": prepared["session"].id,
                "slot_state": (
                    prepared["slot_state"].model_dump(mode="json")
                    if hasattr(prepared.get("slot_state"), "model_dump")
                    else prepared.get("slot_state") or {}
                ),
                "slots_delta": prepared.get("slots_delta") or {},
                "slot_status": prepared.get("slot_status") or "complete",
            }
            async for update in graph.astream(initial, stream_mode="updates"):
                for node_name, node_output in (update or {}).items():
                    event = self.NODE_EVENTS.get(node_name, "tool")
                    status = "error" if event == "error" else "completed"
                    if trace is not None:
                        trace.event(
                            "langgraph.node",
                            {
                                "agent": node_name,
                                "tool": node_name if event == "tool" else None,
                                "status": status,
                                "fallback_reason": (
                                    "langgraph_node_error" if event == "error" else None
                                ),
                            },
                            level="error" if event == "error" else "info",
                        )
                    yield encode_sse(
                        event,
                        {
                            "message": f"{node_name} {status}",
                            "trace_id": trace_id,
                            "node": node_name,
                            "status": status,
                            "fallback_reason": (
                                "langgraph_node_error" if event == "error" else None
                            ),
                        },
                    )
        except Exception:
            if trace is not None:
                trace.event(
                    "langgraph.fallback",
                    {"status": "fallback", "fallback_reason": "langgraph_unavailable"},
                    level="error",
                )
            yield encode_sse(
                "error",
                {
                    "message": "多智能体工作流暂不可用，已继续使用知识库降级回答。",
                    "trace_id": trace_id,
                    "error_code": "LANGGRAPH_FALLBACK",
                    "recoverable": True,
                },
            )

    def _load_graph(self):
        from app.ai.langgraph_agent import compiled_graph

        return compiled_graph

    async def _disconnected(self, callback: Callable[[], Any] | None) -> bool:
        if callback is None:
            return False
        try:
            result = callback()
            return bool(await result) if inspect.isawaitable(result) else bool(result)
        except Exception:
            return False
