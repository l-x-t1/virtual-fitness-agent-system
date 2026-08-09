from __future__ import annotations

import logging

from app.observability.decorators import traced
from app.observability.redaction import redact
from app.observability.tracer import Tracer


def test_langfuse_unconfigured_does_not_break_startup(monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    tracer = Tracer(enabled=True, provider="langfuse")
    trace = tracer.start_trace("startup")
    trace.event("ready", {"status": True})
    trace.finish()
    assert tracer.backend is None


def test_tracing_failure_does_not_affect_decorated_agent():
    class BrokenTrace:
        def event(self, **kwargs):
            raise RuntimeError("backend down")

    class BrokenBackend:
        def trace(self, **kwargs):
            return BrokenTrace()

    tracer = Tracer(enabled=True, backend=BrokenBackend())

    @traced("agent", tracer=tracer)
    def agent(value):
        return value + 1

    assert agent(4) == 5


def test_sensitive_information_is_redacted(caplog):
    secret = "secret-value-123"
    payload = redact(
        {
            "api_key": secret,
            "authorization": f"Bearer {secret}",
            "password": secret,
            "weight_kg": 75,
            "nested": {"cookie": secret, "message": f"token={secret}"},
        }
    )
    assert secret not in str(payload)
    assert payload["weight_kg"] == "[PRIVATE]"
    metrics_payload = redact(
        {
            "input_tokens": 120,
            "output_tokens": 35,
            "first_token_latency_ms": 88,
            "prompt": "身高: 178cm，体重=75kg，体脂率 18%",
        }
    )
    assert metrics_payload["input_tokens"] == 120
    assert metrics_payload["output_tokens"] == 35
    assert "178" not in metrics_payload["prompt"]
    assert "75" not in metrics_payload["prompt"]

    caplog.set_level(logging.INFO, logger="fitness.observability")
    trace = Tracer(enabled=False).start_trace("redaction", metadata={"api_key": secret})
    trace.event("tool", {"password": secret, "status": "ok"})
    assert secret not in caplog.text


def test_trace_captures_required_context_without_private_body_data(caplog):
    caplog.set_level(logging.INFO, logger="fitness.observability")
    trace = Tracer(enabled=False).start_trace(
        "rag",
        trace_id="trace-1",
        session_id="session-1",
        user_id=7,
        metadata={"agent": "coach", "height_cm": 178},
    )
    trace.event("rag.result", {"retrieval_counts": {"bm25": 2, "vector": 2, "graph": 0}})
    assert "trace-1" in caplog.text
    assert "session-1" in caplog.text
    assert "[PRIVATE]" in caplog.text
    assert "178" not in caplog.text


def test_langfuse_v3_observation_api_is_supported():
    calls = []

    class Observation:
        def update_trace(self, **kwargs):
            calls.append(("update_trace", kwargs))

        def create_event(self, **kwargs):
            calls.append(("event", kwargs))

        def update(self, **kwargs):
            calls.append(("update", kwargs))

        def end(self):
            calls.append(("end", {}))

    class Backend:
        def create_trace_id(self, seed=None):
            return "a" * 32

        def start_observation(self, **kwargs):
            calls.append(("start", kwargs))
            return Observation()

    trace = Tracer(enabled=True, provider="langfuse", backend=Backend()).start_trace(
        "agent", session_id="session", user_id=7
    )
    trace.event("tool", {"status": "ok"})
    trace.finish({"answer": "done"})

    assert [name for name, _ in calls] == [
        "start", "update_trace", "event", "event", "event", "update", "end"
    ]
