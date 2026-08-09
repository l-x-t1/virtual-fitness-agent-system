from __future__ import annotations

import functools
import inspect
from typing import Any, Callable

from app.observability.tracer import Tracer, get_tracer


def traced(component: str, name: str | None = None, tracer: Tracer | None = None):
    """Trace sync/async calls without allowing tracing failures to affect them."""

    def decorator(func: Callable):
        operation = name or func.__name__

        if inspect.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                active = tracer or get_tracer()
                trace = active.start_trace(
                    operation,
                    metadata={"component": component, "function": func.__qualname__},
                )
                try:
                    result = await func(*args, **kwargs)
                    trace.finish({"status": "ok"})
                    return result
                except Exception as exc:
                    trace.finish(error=exc)
                    raise

            return async_wrapper

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            active = tracer or get_tracer()
            trace = active.start_trace(
                operation,
                metadata={"component": component, "function": func.__qualname__},
            )
            try:
                result = func(*args, **kwargs)
                trace.finish({"status": "ok"})
                return result
            except Exception as exc:
                trace.finish(error=exc)
                raise

        return sync_wrapper

    return decorator
