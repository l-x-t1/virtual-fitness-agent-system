from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class EvaluationCase:
    id: str
    entrypoint: str
    question: str
    expected_answer: str
    input: dict[str, Any] = field(default_factory=dict)
    expected_citations: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    manual_review: bool = False
    notes: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> EvaluationCase:
        return cls(
            id=str(payload["id"]),
            entrypoint=str(payload.get("entrypoint") or "chat"),
            question=str(payload.get("question") or ""),
            expected_answer=str(payload.get("expected_answer") or ""),
            input=dict(payload.get("input") or {}),
            expected_citations=[str(item) for item in payload.get("expected_citations") or []],
            tags=[str(item) for item in payload.get("tags") or []],
            manual_review=bool(payload.get("manual_review") or False),
            notes=str(payload.get("notes") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "entrypoint": self.entrypoint,
            "question": self.question,
            "expected_answer": self.expected_answer,
            "input": self.input,
            "expected_citations": list(self.expected_citations),
            "tags": list(self.tags),
            "manual_review": self.manual_review,
            "notes": self.notes,
        }


def load_cases(path: str | Path) -> list[EvaluationCase]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("cases") or []
    if not isinstance(payload, list):
        raise ValueError("Evaluation case file must contain a list or {cases: [...]}.")
    return [EvaluationCase.from_dict(item) for item in payload]
