"""Conversation archive helper for persisting changed slots into long-term memory."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

from app.slots.models import SlotState

if TYPE_CHECKING:
    from app.ai.memory import ConversationStore


@dataclass
class ArchiveResult:
    saved: list[dict[str, Any]]
    state: SlotState


class SlotArchiver:
    def __init__(self, memory_store: "ConversationStore | None" = None):
        # Use the project's configured long-term memory store by default.
        if memory_store is None:
            from app.ai.memory import ConversationStore
            memory_store = ConversationStore()
        self.memory_store = memory_store

    def archive(self, *, user_id: int, session_id: str, previous: SlotState | None, current: SlotState) -> ArchiveResult:
        prev = previous or SlotState()
        saved: list[dict[str, Any]] = []
        deltas = self._delta(prev, current)
        for category, content in deltas:
            item = self.memory_store.upsert_long_term_memory(
                user_id,
                {"category": category, "content": content, "importance": 4},
                session_id,
            )
            if item:
                saved.append(item)
        return ArchiveResult(saved=saved, state=current)

    def _delta(self, previous: SlotState, current: SlotState) -> list[tuple[str, str]]:
        results: list[tuple[str, str]] = []
        mapping = {
            "goal": "goal",
            "equipment": "preference",
            "time": "habit",
            "location": "preference",
        }
        for key, category in mapping.items():
            before = getattr(previous, key)
            after = getattr(current, key)
            if before != after and after:
                results.append((category, f"{key}：{after}"))
        if previous.injuries != current.injuries and current.injuries:
            results.append(("body_issue", f"injuries：{'/'.join(current.injuries)}"))
        return results
