from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock
from uuid import uuid4


@dataclass
class Conversation:
    id: str
    user_id: int
    title: str
    messages: list[dict] = field(default_factory=list)
    state: dict = field(default_factory=dict)
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ConversationStore:
    """SQLite-backed AI conversation store, isolated from the project's main database."""

    def __init__(self, max_messages: int = 40, ttl_hours: int | None = None, db_path: str | Path | None = None):
        self.max_messages = max_messages
        self.ttl = timedelta(hours=ttl_hours or int(os.getenv("AI_SESSION_TTL_HOURS", "720")))
        default_path = Path(__file__).with_name("data") / "ai_sessions.db"
        self.db_path = str(db_path or os.getenv("AI_SESSION_DB") or default_path)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.db_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._lock = RLock()
        self._initialize()

    def _initialize(self) -> None:
        with self._lock, self._connection:
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS ai_conversations (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    state_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_ai_conversations_user_updated
                    ON ai_conversations(user_id, updated_at DESC);
                CREATE TABLE IF NOT EXISTS ai_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(conversation_id) REFERENCES ai_conversations(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_ai_messages_conversation
                    ON ai_messages(conversation_id, id);
                """
            )

    def create(self, user_id: int, title: str = "新的训练对话") -> Conversation:
        now = datetime.now(timezone.utc)
        item = Conversation(id=str(uuid4()), user_id=user_id, title=title, updated_at=now)
        with self._lock, self._connection:
            self._connection.execute(
                """INSERT INTO ai_conversations(id, user_id, title, state_json, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (item.id, item.user_id, item.title, "{}", now.isoformat(), now.isoformat()),
            )
        return item

    def get(self, session_id: str, user_id: int) -> Conversation | None:
        with self._lock:
            self.cleanup()
            row = self._connection.execute(
                "SELECT * FROM ai_conversations WHERE id = ? AND user_id = ?",
                (session_id, int(user_id)),
            ).fetchone()
            return self._hydrate(row) if row else None

    def add(self, item: Conversation, role: str, content: str) -> None:
        now = datetime.now(timezone.utc)
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT INTO ai_messages(conversation_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                (item.id, role, content, now.isoformat()),
            )
            stale = self._connection.execute(
                "SELECT id FROM ai_messages WHERE conversation_id = ? ORDER BY id DESC LIMIT -1 OFFSET ?",
                (item.id, self.max_messages),
            ).fetchall()
            if stale:
                self._connection.executemany("DELETE FROM ai_messages WHERE id = ?", [(row["id"],) for row in stale])
            item.messages.append({"role": role, "content": content})
            item.messages = item.messages[-self.max_messages :]
            item.updated_at = now
            self._connection.execute(
                "UPDATE ai_conversations SET updated_at = ? WHERE id = ?",
                (now.isoformat(), item.id),
            )

    def save(self, item: Conversation) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """UPDATE ai_conversations
                   SET title = ?, state_json = ?, updated_at = ?
                   WHERE id = ? AND user_id = ?""",
                (
                    item.title,
                    json.dumps(item.state, ensure_ascii=False),
                    item.updated_at.isoformat(),
                    item.id,
                    item.user_id,
                ),
            )

    def list(self, user_id: int) -> list[Conversation]:
        with self._lock:
            self.cleanup()
            rows = self._connection.execute(
                "SELECT * FROM ai_conversations WHERE user_id = ? ORDER BY updated_at DESC",
                (int(user_id),),
            ).fetchall()
            return [self._hydrate(row) for row in rows]

    def delete(self, session_id: str, user_id: int) -> bool:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                "DELETE FROM ai_conversations WHERE id = ? AND user_id = ?",
                (session_id, int(user_id)),
            )
            return cursor.rowcount > 0

    def cleanup(self) -> None:
        cutoff = (datetime.now(timezone.utc) - self.ttl).isoformat()
        with self._lock, self._connection:
            self._connection.execute("DELETE FROM ai_conversations WHERE updated_at < ?", (cutoff,))

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def _hydrate(self, row: sqlite3.Row) -> Conversation:
        messages = self._connection.execute(
            "SELECT role, content FROM ai_messages WHERE conversation_id = ? ORDER BY id",
            (row["id"],),
        ).fetchall()
        return Conversation(
            id=row["id"],
            user_id=row["user_id"],
            title=row["title"],
            messages=[{"role": item["role"], "content": item["content"]} for item in messages],
            state=json.loads(row["state_json"] or "{}"),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
