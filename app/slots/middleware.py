"""FastAPI middleware hook for slot extraction and conversation state updates."""

from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, Request
from sqlalchemy import text

from app.db.session import SessionLocal
from app.repositories import FitnessRepository
from app.slots.archiver import SlotArchiver
from app.slots.clarifier import SlotClarifier
from app.slots.extractor import SlotExtractor
from app.slots.state import default_slot_store
from app.slots.validator import SlotValidator


SLOT_SESSION_PREFIX = "slot_session_id"


def setup_slot_middleware(app: FastAPI) -> None:
    extractor = SlotExtractor()
    validator = SlotValidator()
    clarifier = SlotClarifier()
    archiver = SlotArchiver()

    @app.middleware("http")
    async def slot_middleware(request: Request, call_next):
        if request.method not in {"POST", "PUT", "PATCH"}:
            return await call_next(request)
        if not request.url.path.startswith("/api/"):
            return await call_next(request)
        body = await request.body()
        if not body:
            return await call_next(request)

        payload = _safe_json(body)
        if not isinstance(payload, dict):
            request._body = body  # type: ignore[attr-defined]
            return await call_next(request)

        user_id = _extract_user_id(request, payload)
        session_id = _extract_session_id(payload)
        if user_id is None or not session_id:
            request._body = body  # type: ignore[attr-defined]
            return await call_next(request)

        message = _extract_message(payload)
        if not message:
            request._body = body  # type: ignore[attr-defined]
            return await call_next(request)

        previous_state = default_slot_store.get(user_id, session_id)
        extracted = extractor.extract(message, history=payload.get("history") or [], state=previous_state)
        merged_state = default_slot_store.merge(user_id, session_id, extracted)
        validation = validator.validate(merged_state)
        decision = clarifier.decide(validation.state)
        request.state.slot_state = decision.state.model_dump()
        request.state.slots_delta = extracted
        request.state.slot_validation_errors = validation.errors
        request.state.slot_clarify = decision.message

        with SessionLocal() as db:
            repo = FitnessRepository(db)
            state_json = json.dumps(decision.state.model_dump(mode="json"), ensure_ascii=False)
            _ensure_conversation_snapshot(repo, session_id, user_id, state_json)
            _ensure_dialog_slot_row(repo, session_id, user_id, extracted)
            _ensure_message_row(repo, session_id, user_id, payload, extracted)
            db.commit()

        if decision.should_fallback:
            archiver.archive(user_id=user_id, session_id=session_id, previous=previous_state, current=decision.state)
        request._body = body  # type: ignore[attr-defined]
        return await call_next(request)


def _safe_json(body: bytes) -> dict[str, Any] | None:
    try:
        parsed = json.loads(body.decode("utf-8"))
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def _extract_user_id(request: Request, payload: dict[str, Any]) -> int | None:
    for candidate in (payload.get("user_id"), getattr(request.state, "user_id", None), request.headers.get("X-User-Id")):
        try:
            if candidate is not None:
                return int(candidate)
        except (TypeError, ValueError):
            continue
    return None


def _extract_session_id(payload: dict[str, Any]) -> str | None:
    for key in ("session_id", "conversation_id", SLOT_SESSION_PREFIX):
        value = payload.get(key)
        if value:
            return str(value)
    return None


def _extract_message(payload: dict[str, Any]) -> str | None:
    for key in ("message", "content", "text", "query"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _ensure_conversation_snapshot(repo: FitnessRepository, session_id: str, user_id: int, state_json: str) -> None:
    repo.session.execute(text(
        """
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            state_json TEXT NOT NULL DEFAULT '{}'
        )
        """
    ))
    repo.session.execute(text(
        """
        INSERT INTO conversations(id, user_id, state_json)
        VALUES (:id, :user_id, :state_json)
        ON CONFLICT(id) DO UPDATE SET state_json = excluded.state_json
        """,
    ),
        {"id": session_id, "user_id": int(user_id), "state_json": state_json},
    )


def _ensure_dialog_slot_row(repo: FitnessRepository, session_id: str, user_id: int, extracted: dict[str, Any]) -> None:
    repo.session.execute(text(
        """
        CREATE TABLE IF NOT EXISTS dialog_slots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            slot_name TEXT NOT NULL,
            slot_value TEXT NOT NULL,
            source TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    ))
    for key, value in extracted.items():
        if value is None:
            continue
        repo.session.execute(text(
            """
            INSERT INTO dialog_slots(conversation_id, user_id, slot_name, slot_value, source)
            VALUES (:conversation_id, :user_id, :slot_name, :slot_value, :source)
            """,
        ),
            {
                "conversation_id": session_id,
                "user_id": int(user_id),
                "slot_name": key,
                "slot_value": json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value),
                "source": "llm",
            },
        )


def _ensure_message_row(repo: FitnessRepository, session_id: str, user_id: int, payload: dict[str, Any], extracted: dict[str, Any]) -> None:
    repo.session.execute(text(
        """
        CREATE TABLE IF NOT EXISTS conversation_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            intent TEXT,
            slots_delta TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    ))
    repo.session.execute(text(
        """
        INSERT INTO conversation_messages(conversation_id, user_id, role, content, intent, slots_delta)
        VALUES (:conversation_id, :user_id, :role, :content, :intent, :slots_delta)
        """,
    ),
        {
            "conversation_id": session_id,
            "user_id": int(user_id),
            "role": payload.get("role") or "user",
            "content": _extract_message(payload) or "",
            "intent": payload.get("intent") or "slot_extraction",
            "slots_delta": json.dumps(extracted, ensure_ascii=False),
        },
    )
