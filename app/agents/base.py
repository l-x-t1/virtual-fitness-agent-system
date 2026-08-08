from __future__ import annotations

import asyncio
import importlib
import json
from typing import Any

from pydantic import BaseModel

from app.agents.output_parser import LLMOutputError, OutputParser
from app.llm import LLMClient, LLMConfigurationError, LLMInvocationError


class BaseAgent:
    """Common prompt, invocation, validation, and runtime metadata behavior."""

    prompt_module: str | None = None
    output_schema: type[BaseModel] | None = None

    def __init__(
        self,
        llm_client: LLMClient | Any | None = None,
        output_parser: OutputParser | None = None,
        prompt_module: str | None = None,
        output_schema: type[BaseModel] | None = None,
    ):
        self.llm_client = llm_client or LLMClient()
        self.output_parser = output_parser or OutputParser()
        self.prompt_module = prompt_module or self.prompt_module
        self.output_schema = output_schema or self.output_schema

    def tools(self) -> list[Any]:
        return []

    def run(
        self,
        input_data: dict[str, Any],
        *,
        tools: list[Any] | None = None,
    ) -> dict[str, Any]:
        client = self._bound_client(tools)
        raw_output = client.invoke(self.build_prompt(input_data))
        return self._parse(raw_output)

    async def arun(
        self,
        input_data: dict[str, Any],
        *,
        tools: list[Any] | None = None,
    ) -> dict[str, Any]:
        prompt = self.build_prompt(input_data)
        client = self._bound_client(tools)
        ainvoke = getattr(client, "ainvoke", None)
        if ainvoke is not None:
            raw_output = await ainvoke(prompt)
        else:
            raw_output = await asyncio.to_thread(client.invoke, prompt)
        return self._parse(raw_output)

    def build_prompt(self, input_data: dict[str, Any]) -> str:
        template = self.load_prompt()
        payload = json.dumps(input_data, ensure_ascii=False, indent=2, default=str)
        return template.format(input_json=payload)

    def load_prompt(self) -> str:
        if not self.prompt_module:
            raise ValueError("prompt_module is required for BaseAgent.")
        module = importlib.import_module(self.prompt_module)
        prompt = getattr(module, "PROMPT_TEMPLATE", None)
        if not prompt:
            raise ValueError(f"{self.prompt_module} must define PROMPT_TEMPLATE.")
        return str(prompt)

    def online_metadata(self) -> dict[str, str]:
        config = getattr(self.llm_client, "config", None)
        return {
            "mode": "online",
            "provider": str(getattr(config, "provider", "mock")),
            "model": str(getattr(config, "model", "mock")),
        }

    def fallback_metadata(self, exc: Exception | None = None, reason: str | None = None) -> dict[str, str]:
        config = getattr(self.llm_client, "config", None)
        return {
            "mode": "fallback",
            "provider": str(getattr(config, "provider", "unconfigured")),
            "model": str(getattr(config, "model", "")),
            "fallback_reason": reason or self._safe_reason(exc),
        }

    def _parse(self, raw_output: str) -> dict[str, Any]:
        if self.output_schema is None:
            return self.output_parser.loads(raw_output)
        return self.output_parser.parse(raw_output, self.output_schema)

    def _safe_reason(self, exc: Exception | None) -> str:
        if isinstance(exc, LLMConfigurationError):
            return "missing_or_invalid_llm_configuration"
        if isinstance(exc, LLMInvocationError):
            return "llm_request_failed"
        if isinstance(exc, (LLMOutputError, ValueError)):
            return "invalid_model_output"
        if exc is None:
            return "offline_fallback"
        return "llm_unavailable"

    @property
    def recoverable_errors(self) -> tuple[type[Exception], ...]:
        return (LLMConfigurationError, LLMInvocationError, LLMOutputError, ValueError, RuntimeError)

    def _bound_client(self, tools: list[Any] | None = None):
        tool_defs = list(tools if tools is not None else self.tools())
        if not tool_defs:
            return self.llm_client
        binder = getattr(self.llm_client, "bind_tools", None)
        if callable(binder):
            return binder(tool_defs)
        return self.llm_client
