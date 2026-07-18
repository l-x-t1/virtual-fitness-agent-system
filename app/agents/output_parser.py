from __future__ import annotations

import json
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

ModelT = TypeVar("ModelT", bound=BaseModel)


class OutputParser:
    """Parse and validate JSON returned by an LLM."""

    def parse(self, text: str, schema: type[ModelT]) -> dict[str, Any]:
        payload = self.loads(text)
        try:
            return schema.model_validate(payload).model_dump()
        except ValidationError as exc:
            raise ValueError(f"LLM output does not match schema: {exc}") from exc

    def loads(self, text: str) -> Any:
        cleaned = self._strip_code_fence(text)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            extracted = self._extract_json(cleaned)
            return json.loads(extracted)

    def _strip_code_fence(self, text: str) -> str:
        value = text.strip()
        if not value.startswith("```"):
            return value
        lines = value.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()

    def _extract_json(self, text: str) -> str:
        start = min(
            [index for index in (text.find("{"), text.find("[")) if index >= 0],
            default=-1,
        )
        if start < 0:
            raise ValueError("LLM output does not contain JSON.")

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
        raise ValueError("LLM output contains incomplete JSON.")
