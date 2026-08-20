from __future__ import annotations

import importlib.util
from typing import Any

from app.tools.registry import ToolRegistry, tool_result


class MCPAdapter:
    """Optional MCP extension point; local tools remain the guaranteed runtime."""

    def __init__(self, local_registry: ToolRegistry):
        self.local_registry = local_registry

    @property
    def available(self) -> bool:
        return importlib.util.find_spec("mcp") is not None

    def status(self) -> dict[str, Any]:
        return tool_result(
            ok=True,
            mode="mcp" if self.available else "local",
            source="mcp-adapter" if self.available else "local-registry",
            data={"mcp_available": self.available, "local_tools": self.local_registry.names()},
            fallback_reason=None if self.available else "mcp_sdk_unavailable",
        )

    def tools(self):
        return self.local_registry.specs()
