from __future__ import annotations

import importlib
import json
from typing import Any

from pydantic import BaseModel

from app.agents.output_parser import OutputParser
from app.llm import LLMClient


class BaseAgent:
    """Common runtime for LLM-driven agents with prompt loading and JSON parsing."""

    prompt_module: str | None = None
    output_schema: type[BaseModel] | None = None

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        output_parser: OutputParser | None = None,
        prompt_module: str | None = None,
        output_schema: type[BaseModel] | None = None,
    ):
        self.llm_client = llm_client or LLMClient()
        self.output_parser = output_parser or OutputParser()
        self.prompt_module = prompt_module or self.prompt_module
        self.output_schema = output_schema or self.output_schema

    def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        prompt = self.build_prompt(input_data)
        raw_output = self.llm_client.invoke(prompt)
        if self.output_schema is None:
            return self.output_parser.loads(raw_output)
        return self.output_parser.parse(raw_output, self.output_schema)

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
