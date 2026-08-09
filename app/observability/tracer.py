from __future__ import annotations

import json
import logging
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Thread
from typing import Any, Iterator
from uuid import NAMESPACE_URL, uuid4, uuid5

from app.observability.metrics import metrics
from app.observability.redaction import redact

logger = logging.getLogger("fitness.observability")


class _LangSmithTrace:
    def __init__(self, run: Any):
        self.run = run
        self.output: Any = None
        self.error: str | None = None

    def event(self, name: str, metadata: dict[str, Any], **_: Any) -> None:
        self.run.add_event(
            {"name": name, "time": datetime.now(timezone.utc), "metadata": metadata}
        )

    def update(self, output: Any = None, status_message: str | None = None, **_: Any) -> None:
        self.output = output
        if status_message and status_message != "completed":
            self.error = status_message

    def end(self) -> None:
        self.run.end(outputs={"output": self.output}, error=self.error)
        Thread(target=self._post, name="langsmith-trace", daemon=True).start()

    def _post(self) -> None:
        try:
            self.run.post()
        except Exception:
            metrics.increment("observability.backend_failures")


class _LangSmithBackend:
    def __init__(self, client: Any, project: str):
        self.client = client
        self.project = project

    def trace(
        self,
        *,
        id: str,
        name: str,
        session_id: str | None = None,
        user_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> _LangSmithTrace:
        from langsmith.run_trees import RunTree

        run = RunTree(
            id=uuid5(NAMESPACE_URL, id),
            name=name,
            run_type="chain",
            inputs={},
            extra={
                "metadata": {
                    **(metadata or {}),
                    "session_id": session_id,
                    "user_id": user_id,
                    "application_trace_id": id,
                }
            },
            project_name=self.project,
            ls_client=self.client,
        )
        return _LangSmithTrace(run)


@dataclass
class TraceContext:
    tracer: "Tracer"
    trace_id: str
    name: str
    session_id: str | None = None
    user_id: int | str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    backend_trace: Any | None = None
    started_at: float = field(default_factory=time.perf_counter)

    def event(self, name: str, data: dict[str, Any] | None = None, level: str = "info") -> None:
        self.tracer.event(self, name, data or {}, level=level)

    @contextmanager
    def span(self, name: str, **metadata: Any) -> Iterator[dict[str, Any]]:
        started = time.perf_counter()
        state: dict[str, Any] = {"status": "ok"}
        self.event(f"{name}.start", metadata)
        try:
            yield state
        except Exception as exc:
            state["status"] = "error"
            state["error"] = type(exc).__name__
            raise
        finally:
            elapsed = (time.perf_counter() - started) * 1000
            metrics.timing(f"{name}.latency_ms", elapsed)
            self.event(
                f"{name}.end",
                {**metadata, **state, "latency_ms": round(elapsed, 3)},
                level="error" if state["status"] == "error" else "info",
            )

    def finish(self, output: Any = None, error: Exception | None = None) -> None:
        elapsed = (time.perf_counter() - self.started_at) * 1000
        self.event(
            "trace.done" if error is None else "trace.error",
            {
                "status": "ok" if error is None else "error",
                "latency_ms": round(elapsed, 3),
                "output": output,
                "error": type(error).__name__ if error else None,
            },
            level="error" if error else "info",
        )
        self.tracer.finish_backend(self, output=output, error=error)


class Tracer:
    """Failure-isolated Langfuse/LangSmith tracer with redacted local logging."""

    def __init__(
        self,
        enabled: bool | None = None,
        provider: str | None = None,
        backend: Any | None = None,
    ):
        self.enabled = self._enabled(enabled)
        self.provider = (provider or os.getenv("OBSERVABILITY_PROVIDER", "langfuse")).strip().lower()
        self.backend = backend if backend is not None else self._build_backend()

    def start_trace(
        self,
        name: str,
        *,
        trace_id: str | None = None,
        session_id: str | None = None,
        user_id: int | str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TraceContext:
        resolved_id = trace_id or str(uuid4())
        safe_metadata = redact(metadata or {})
        backend_trace = None
        if self.enabled and self.backend is not None:
            try:
                factory = getattr(self.backend, "trace", None)
                if callable(factory):
                    backend_trace = factory(
                        id=resolved_id,
                        name=name,
                        session_id=session_id,
                        user_id=str(user_id) if user_id is not None else None,
                        metadata=safe_metadata,
                    )
                else:
                    start_observation = getattr(self.backend, "start_observation", None)
                    create_trace_id = getattr(self.backend, "create_trace_id", None)
                    if callable(start_observation) and callable(create_trace_id):
                        backend_id = create_trace_id(seed=resolved_id)
                        backend_trace = start_observation(
                            trace_context={"trace_id": backend_id},
                            name=name,
                            as_type="agent",
                            metadata={"application_trace_id": resolved_id, **safe_metadata},
                        )
                        update_trace = getattr(backend_trace, "update_trace", None)
                        if callable(update_trace):
                            update_trace(
                                name=name,
                                session_id=session_id,
                                user_id=str(user_id) if user_id is not None else None,
                                metadata={"application_trace_id": resolved_id, **safe_metadata},
                            )
            except Exception:
                metrics.increment("observability.backend_failures")
        trace = TraceContext(
            tracer=self,
            trace_id=resolved_id,
            name=name,
            session_id=session_id,
            user_id=user_id,
            metadata=safe_metadata,
            backend_trace=backend_trace,
        )
        self.event(trace, "trace.start", {"name": name, **safe_metadata})
        return trace

    def event(self, trace: TraceContext, name: str, data: dict[str, Any], level: str = "info") -> None:
        try:
            safe_data = redact(data)
            payload = {
                "trace_id": trace.trace_id,
                "session_id": trace.session_id,
                "user_id": trace.user_id,
                "event": name,
                "level": level,
                "data": safe_data,
            }
            log = logger.error if level == "error" else logger.info
            log("observability %s", json.dumps(payload, ensure_ascii=False, default=str))
            metrics.increment(f"events.{name}")
            if trace.backend_trace is not None:
                emitter = getattr(trace.backend_trace, "event", None)
                if not callable(emitter):
                    emitter = getattr(trace.backend_trace, "create_event", None)
                if callable(emitter):
                    emitter(
                        name=name,
                        metadata=safe_data,
                        level="ERROR" if level == "error" else "DEFAULT",
                    )
            elif self.enabled and self.backend is not None:
                emitter = getattr(self.backend, "event", None)
                if callable(emitter):
                    emitter(name=name, trace_id=trace.trace_id, metadata=safe_data)
        except Exception:
            metrics.increment("observability.event_failures")

    def finish_backend(
        self,
        trace: TraceContext,
        *,
        output: Any = None,
        error: Exception | None = None,
    ) -> None:
        if trace.backend_trace is None:
            return
        try:
            safe_output = redact(output)
            updater = getattr(trace.backend_trace, "update", None)
            if callable(updater):
                updater(
                    output=safe_output,
                    level="ERROR" if error else "DEFAULT",
                    status_message=type(error).__name__ if error else "completed",
                )
            end = getattr(trace.backend_trace, "end", None)
            if callable(end):
                end()
        except Exception:
            metrics.increment("observability.backend_failures")

    def _build_backend(self) -> Any | None:
        if not self.enabled:
            return None
        try:
            if self.provider == "langfuse":
                public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "").strip()
                secret_key = os.getenv("LANGFUSE_SECRET_KEY", "").strip()
                if not public_key or not secret_key:
                    return None
                from langfuse import Langfuse

                kwargs = {"public_key": public_key, "secret_key": secret_key}
                if os.getenv("LANGFUSE_HOST", "").strip():
                    kwargs["host"] = os.getenv("LANGFUSE_HOST", "").strip()
                return Langfuse(**kwargs)
            if self.provider == "langsmith":
                if not os.getenv("LANGSMITH_API_KEY", "").strip():
                    return None
                from langsmith import Client

                client = Client(api_key=os.getenv("LANGSMITH_API_KEY"))
                project = os.getenv("LANGSMITH_PROJECT", "virtual-fitness-agent-system").strip()
                return _LangSmithBackend(client, project)
        except Exception:
            metrics.increment("observability.initialization_failures")
        return None

    def _enabled(self, value: bool | None) -> bool:
        if value is not None:
            return bool(value)
        return os.getenv("OBSERVABILITY_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


_default_tracer: Tracer | None = None


def get_tracer() -> Tracer:
    global _default_tracer
    if _default_tracer is None:
        _default_tracer = Tracer()
    return _default_tracer
