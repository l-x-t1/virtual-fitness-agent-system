from __future__ import annotations

import inspect
from functools import wraps
from typing import Any

from app.llm.client import ToolSpec


def tool_result(
    *,
    ok: bool,
    mode: str,
    source: str,
    data: Any = None,
    fallback_reason: str | None = None,
) -> dict[str, Any]:
    """Return the public, non-sensitive result envelope used by every tool."""
    return {
        "ok": bool(ok),
        "mode": mode,
        "source": source,
        "data": data if data is not None else {},
        "fallback_reason": fallback_reason,
    }


class ToolRegistry:
    """Small local registry compatible with the existing ``LLMClient.bind_tools``."""

    def __init__(self, tools: list[ToolSpec] | None = None):
        self._tools: dict[str, ToolSpec] = {}
        self.results: list[dict[str, Any]] = []
        for item in tools or []:
            self.register(item)

    def register(self, tool: ToolSpec) -> ToolSpec:
        if not isinstance(tool, ToolSpec):
            raise TypeError("tool must be a ToolSpec")
        if not tool.name or not callable(tool.handler):
            raise ValueError("tool name and handler are required")
        original = tool.handler
        if inspect.iscoroutinefunction(original):
            @wraps(original)
            async def async_handler(**arguments: Any):
                try:
                    raw = await original(**arguments)
                    result = self._normalize_result(raw, tool.name)
                except Exception:
                    result = tool_result(
                        ok=False, mode="fallback", source=tool.name,
                        fallback_reason="tool_execution_failed",
                    )
                self.results.append({"tool": tool.name, "result": result})
                return result

            handler = async_handler
        else:
            @wraps(original)
            def sync_handler(**arguments: Any):
                try:
                    raw = original(**arguments)
                    if inspect.isawaitable(raw):
                        raise RuntimeError("async_tool_used_in_sync_mode")
                    result = self._normalize_result(raw, tool.name)
                except Exception:
                    result = tool_result(
                        ok=False, mode="fallback", source=tool.name,
                        fallback_reason="tool_execution_failed",
                    )
                self.results.append({"tool": tool.name, "result": result})
                return result

            handler = sync_handler
        registered = ToolSpec(
            name=tool.name,
            description=tool.description,
            handler=handler,
            parameters=tool.parameters,
        )
        self._tools[tool.name] = registered
        return registered

    def specs(self) -> list[ToolSpec]:
        return list(self._tools.values())

    def names(self) -> list[str]:
        return list(self._tools)

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def call(self, name: str, **arguments: Any) -> dict[str, Any]:
        tool = self.get(name)
        if tool is None:
            result = tool_result(
                ok=False,
                mode="fallback",
                source="local-registry",
                fallback_reason="tool_not_found",
                data={"tool": name},
            )
            self.results.append({"tool": name, "result": result})
            return result
        try:
            result = tool.handler(**arguments)
            if inspect.isawaitable(result):
                raise RuntimeError("async_tool_used_in_sync_mode")
            result = self._normalize_result(result, name)
        except Exception:
            result = tool_result(
                ok=False,
                mode="fallback",
                source=name,
                fallback_reason="tool_execution_failed",
            )
        if not self.results or self.results[-1] != {"tool": name, "result": result}:
            self.results.append({"tool": name, "result": result})
        return result

    async def acall(self, name: str, **arguments: Any) -> dict[str, Any]:
        tool = self.get(name)
        if tool is None:
            return self.call(name, **arguments)
        try:
            result = tool.handler(**arguments)
            if inspect.isawaitable(result):
                result = await result
            result = self._normalize_result(result, name)
        except Exception:
            result = tool_result(
                ok=False,
                mode="fallback",
                source=name,
                fallback_reason="tool_execution_failed",
            )
        if not self.results or self.results[-1] != {"tool": name, "result": result}:
            self.results.append({"tool": name, "result": result})
        return result

    def _normalize_result(self, result: Any, source: str) -> dict[str, Any]:
        if isinstance(result, dict) and {
            "ok", "mode", "source", "data", "fallback_reason"
        }.issubset(result):
            return result
        return tool_result(ok=True, mode="local", source=source, data=result)
