from __future__ import annotations

import json
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

ModelT = TypeVar("ModelT", bound=BaseModel)


class LLMOutputError(ValueError):
    """Raised when model output cannot be parsed or validated."""


class OutputParser:
    """Extract JSON from plain text or Markdown and validate it with Pydantic."""

    def parse(self, text: str, schema: type[ModelT]) -> dict[str, Any]:
        payload = self.loads(text)
        try:
            return schema.model_validate(payload).model_dump()
        except ValidationError:
            raise LLMOutputError("LLM output does not match the required JSON schema.") from None

    def loads(self, text: str) -> Any:
        if not isinstance(text, str) or not text.strip():
            raise LLMOutputError("LLM output is empty.")
        cleaned = self._strip_code_fence(text)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            try:
                return json.loads(self._extract_json(cleaned))
            except json.JSONDecodeError:
                raise LLMOutputError("LLM output contains invalid JSON.") from None

    def _strip_code_fence(self, text: str) -> str:
        value = text.strip()
        if not value.startswith("```"):
            return value
        lines = value.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()

    def _extract_json(self, text: str) -> str:
        starts = [index for index in (text.find("{"), text.find("[")) if index >= 0]
        if not starts:
            raise LLMOutputError("LLM output does not contain JSON.")
        start = min(starts)
        opening = text[start]
        closing = "}" if opening == "{" else "]"
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            char = text[index]
            if escaped:
                escaped = False
                continue
            if char == "\\":
                escaped = True
                continue
            if char == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if char == opening:
                depth += 1
            elif char == closing:
                depth -= 1
                if depth == 0:
                    return text[start:index + 1]
        raise LLMOutputError("LLM output contains incomplete JSON.")
