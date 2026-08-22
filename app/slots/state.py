"""Redis-backed slot state tree with in-memory fallback."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Any

from app.cache.redis_client import redis_client
from app.core.config import settings
from app.slots.models import SlotState


@dataclass
class SlotSnapshot:
    session_id: str
    user_id: int
    state: SlotState
    expires_at: datetime

    def expired(self) -> bool:
        return datetime.now(timezone.utc) >= self.expires_at


class SlotStore:
    """Stateful slot store supporting TTL and incremental merge."""

    def __init__(self, ttl_seconds: int | None = None):
        self.ttl_seconds = int(ttl_seconds or getattr(settings, "slot_ttl_seconds", 3600))
        self._local: dict[str, SlotSnapshot] = {}
        self._lock = RLock()

    def _key(self, user_id: int, session_id: str) -> str:
        return f"slot_state:{int(user_id)}:{session_id}"

    def get(self, user_id: int, session_id: str) -> SlotState:
        client = redis_client()
        key = self._key(user_id, session_id)
        if client:
            raw = client.get(key)
            if raw:
                return SlotState.model_validate_json(raw)
        with self._lock:
            snapshot = self._local.get(key)
            if snapshot and not snapshot.expired():
                return snapshot.state
            if snapshot and snapshot.expired():
                self._local.pop(key, None)
        return SlotState()

    def set(self, user_id: int, session_id: str, state: SlotState) -> SlotState:
        payload = state.model_copy()
        payload.updated_at = datetime.now(timezone.utc)
        key = self._key(user_id, session_id)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=self.ttl_seconds)
        client = redis_client()
        if client:
            client.setex(key, self.ttl_seconds, payload.model_dump_json())
        with self._lock:
            self._local[key] = SlotSnapshot(session_id=session_id, user_id=int(user_id), state=payload, expires_at=expires_at)
        return payload

    def merge(self, user_id: int, session_id: str, delta: dict[str, Any] | SlotState | None) -> SlotState:
        current = self.get(user_id, session_id)
        if delta is None:
            return self.set(user_id, session_id, current.set_missing_required())
        merged = current.merged(delta.model_dump() if isinstance(delta, SlotState) else delta)
        merged.set_missing_required()
        return self.set(user_id, session_id, merged)

    def touch(self, user_id: int, session_id: str) -> SlotState:
        current = self.get(user_id, session_id)
        return self.set(user_id, session_id, current)

    def clear(self, user_id: int, session_id: str) -> None:
        key = self._key(user_id, session_id)
        client = redis_client()
        if client:
            client.delete(key)
        with self._lock:
            self._local.pop(key, None)


default_slot_store = SlotStore()

