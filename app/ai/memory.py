from __future__ import annotations

import json
import os
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4

from app.embeddings import SemanticEmbeddings
from app.vectorstore import ChromaVectorStore


DEFAULT_SHORT_TERM_TURNS = 10
DEFAULT_LONG_TERM_TOP_K = 6
DEFAULT_SUMMARY_EVERY_TURNS = 100


@dataclass
class Conversation:
    id: str
    user_id: int
    title: str
    messages: list[dict] = field(default_factory=list)
    state: dict = field(default_factory=dict)
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class MemoryContext:
    short_term_messages: list[dict]
    long_term_memories: list[dict]
    summary_memories: list[dict]

    def as_system_prompt(self) -> str:
        sections = []
        if self.summary_memories:
            lines = [
                f"- {item['summary']}"
                for item in self.summary_memories
                if str(item.get("summary") or "").strip()
            ]
            if lines:
                sections.append("【总结记忆】\n" + "\n".join(lines))
        if self.long_term_memories:
            lines = [
                f"- {item['category']}：{item['content']}"
                for item in self.long_term_memories
                if str(item.get("content") or "").strip()
            ]
            if lines:
                sections.append("【长期记忆】\n" + "\n".join(lines))
        if not sections:
            return "暂无可用的跨会话记忆。"
        return (
            "以下是系统自动检索到的用户记忆，只作为个性化参考；"
            "不得编造未出现过的健康问题或身体指标。\n" + "\n\n".join(sections)
        )


class ConversationStore:
    """SQLite-backed three-layer memory store isolated from the main database."""

    def __init__(self, max_messages: int | None = None, ttl_hours: int | None = None, db_path: str | Path | None = None):
        self.short_term_turns = int(os.getenv("AI_SHORT_TERM_TURNS", str(DEFAULT_SHORT_TERM_TURNS)))
        self.max_messages = max_messages or self.short_term_turns * 2
        self.ttl = timedelta(hours=ttl_hours or int(os.getenv("AI_SESSION_TTL_HOURS", "720")))
        self.long_term_top_k = int(os.getenv("AI_LONG_TERM_TOP_K", str(DEFAULT_LONG_TERM_TOP_K)))
        self.summary_every_turns = int(os.getenv("AI_SUMMARY_EVERY_TURNS", str(DEFAULT_SUMMARY_EVERY_TURNS)))
        self.embeddings = SemanticEmbeddings()
        default_path = Path(__file__).with_name("data") / "ai_sessions.db"
        self.db_path = str(db_path or os.getenv("AI_SESSION_DB") or default_path)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.db_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._lock = RLock()
        self._long_term_store = ChromaVectorStore(
            collection_name="ai-long-term-memory",
            embeddings=self.embeddings,
            persist_directory=os.getenv("CHROMA_PERSIST_DIRECTORY"),
        )
        self._summary_store = ChromaVectorStore(
            collection_name="ai-memory-summaries",
            embeddings=self.embeddings,
            persist_directory=os.getenv("CHROMA_PERSIST_DIRECTORY"),
        )
        self._memory_index_signature: tuple[str, ...] = ()
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
                CREATE TABLE IF NOT EXISTS ai_long_term_memories (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    category TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source_session_id TEXT,
                    importance REAL NOT NULL DEFAULT 3,
                    embedding_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_ai_long_term_user_updated
                    ON ai_long_term_memories(user_id, updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_ai_long_term_user_category
                    ON ai_long_term_memories(user_id, category);
                CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_long_term_user_category_content
                    ON ai_long_term_memories(user_id, category, content);
                CREATE TABLE IF NOT EXISTS ai_memory_summaries (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    session_id TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    message_count INTEGER NOT NULL,
                    embedding_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_ai_memory_summaries_user_updated
                    ON ai_memory_summaries(user_id, updated_at DESC);
                CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_memory_summaries_session
                    ON ai_memory_summaries(user_id, session_id);
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

    def recent_messages(self, item: Conversation, turns: int | None = None) -> list[dict]:
        limit = max(1, int(turns or self.short_term_turns)) * 2
        return list(item.messages[-limit:])

    def context(
        self,
        user_id: int,
        *,
        session: Conversation | None = None,
        query: str = "",
        short_term_turns: int | None = None,
        long_term_top_k: int | None = None,
    ) -> MemoryContext:
        return MemoryContext(
            short_term_messages=self.recent_messages(session, short_term_turns) if session else [],
            long_term_memories=self.search_long_term(user_id, query, long_term_top_k or self.long_term_top_k),
            summary_memories=self.latest_summaries(user_id, limit=2),
        )

    def search_long_term(self, user_id: int, query: str, top_k: int | None = None) -> list[dict]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM ai_long_term_memories WHERE user_id = ? ORDER BY updated_at DESC",
                (int(user_id),),
            ).fetchall()
        if not rows:
            return []

        query_vector = self.embeddings.embed_query(query or "训练计划 用户画像 健身建议")
        planning_query = bool(re.search(r"计划|推荐|训练|动作|安排|减脂|增肌|plan|recommend|workout", query, re.I))
        semantic_scores = self._semantic_memory_scores(rows, user_id, query or "训练计划 用户画像 健身建议")
        ranked = []
        for row in rows:
            item = self._memory_row(row)
            similarity = semantic_scores.get(str(row["id"]))
            if similarity is None:
                vector = self.embeddings.embed_query(f"{item['category']}：{item['content']}")
                similarity = self._cosine(query_vector, vector)
            category = item["category"]
            boost = {
                "body_issue": 0.35,
                "goal": 0.2,
                "preference": 0.16,
                "habit": 0.14,
                "age": 0.08,
            }.get(category, 0.05)
            if planning_query and category in {"body_issue", "goal", "preference", "habit"}:
                boost += 0.25
            score = max(0.0, similarity) + boost + float(item["importance"]) / 100.0
            ranked.append((score, item))
        ranked.sort(key=lambda pair: pair[0], reverse=True)
        limit = max(1, int(top_k or self.long_term_top_k))
        return [{**item, "score": round(score, 4)} for score, item in ranked[:limit]]

    def _semantic_memory_scores(
        self,
        rows: list[sqlite3.Row],
        user_id: int,
        query: str,
    ) -> dict[str, float]:
        try:
            signature = tuple(sorted(str(row["id"]) for row in rows))
            if signature != self._memory_index_signature:
                self._long_term_store.upsert(
                    ids=[f"memory-{row['id']}" for row in rows],
                    documents=[f"{row['category']}：{row['content']}" for row in rows],
                    metadatas=[
                        {
                            "memory_id": str(row["id"]),
                            "user_id": int(row["user_id"]),
                            "category": str(row["category"]),
                            "source": "long_term_memory",
                        }
                        for row in rows
                    ],
                )
                self._memory_index_signature = signature
            hits = self._long_term_store.query(
                query,
                n_results=min(max(1, self.long_term_top_k), len(rows)),
                where={"user_id": int(user_id)},
            )
            return {
                str((hit.get("metadata") or {}).get("memory_id")): self._distance_to_similarity(hit.get("distance"))
                for hit in hits
                if (hit.get("metadata") or {}).get("memory_id")
            }
        except Exception:
            return {}

    def latest_summaries(self, user_id: int, session_id: str | None = None, limit: int = 2) -> list[dict]:
        params: list[Any] = [int(user_id)]
        where = "user_id = ?"
        if session_id:
            where += " AND session_id = ?"
            params.append(session_id)
        params.append(max(1, int(limit)))
        with self._lock:
            rows = self._connection.execute(
                f"SELECT * FROM ai_memory_summaries WHERE {where} ORDER BY updated_at DESC LIMIT ?",
                params,
            ).fetchall()
        return [
            {
                "id": row["id"],
                "user_id": row["user_id"],
                "session_id": row["session_id"],
                "summary": row["summary"],
                "message_count": row["message_count"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    def remember_turn(
        self,
        *,
        user_id: int,
        session: Conversation,
        user_message: str,
        assistant_message: str,
        llm: Any | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> dict:
        extracted = self.extract_long_term_memories(user_message, assistant_message, llm, provider, model)
        saved = [self.upsert_long_term_memory(user_id, item, session.id) for item in extracted]
        summary = self.maybe_update_summary(session, llm, provider, model)
        return {
            "long_term_saved": [item for item in saved if item],
            "summary_updated": bool(summary),
            "summary": summary,
        }

    def extract_long_term_memories(
        self,
        user_message: str,
        assistant_message: str = "",
        llm: Any | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> list[dict]:
        if llm is not None:
            try:
                raw = llm.chat(
                    [
                        {
                            "role": "system",
                            "content": (
                                "你是健身智能记忆抽取器。只抽取长期稳定、未来训练会反复用到的信息；"
                                "不要抽取一次性问题、寒暄或模型自己的建议。"
                            ),
                        },
                        {
                            "role": "user",
                            "content": (
                                "从以下对话抽取长期记忆，返回 JSON 数组。每项格式："
                                '{"category":"age|goal|habit|body_issue|preference|limitation|other",'
                                '"content":"简短事实","importance":1-5}。\n'
                                f"用户：{user_message}\nAI：{assistant_message}"
                            ),
                        },
                    ],
                    provider,
                    model,
                    temperature=0,
                )
                items = self._parse_memory_items(raw)
                if items:
                    return items
            except Exception:
                pass
        return self._fallback_extract_memories(user_message)

    def upsert_long_term_memory(self, user_id: int, item: dict, session_id: str | None = None) -> dict | None:
        category = self._normalize_category(item.get("category"))
        content = re.sub(r"\s+", " ", str(item.get("content") or "")).strip(" ;；。")
        if not content:
            return None
        importance = max(1.0, min(float(item.get("importance") or 3), 5.0))
        now = datetime.now(timezone.utc).isoformat()
        memory_id = str(uuid4())
        embedding = self.embeddings.embed_query(f"{category}：{content}")
        payload = json.dumps(embedding, ensure_ascii=False)
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO ai_long_term_memories(
                    id, user_id, category, content, source_session_id, importance,
                    embedding_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, category, content) DO UPDATE SET
                    source_session_id = excluded.source_session_id,
                    importance = max(ai_long_term_memories.importance, excluded.importance),
                    embedding_json = excluded.embedding_json,
                    updated_at = excluded.updated_at
                """,
                (memory_id, int(user_id), category, content, session_id, importance, payload, now, now),
            )
            row = self._connection.execute(
                "SELECT id FROM ai_long_term_memories WHERE user_id = ? AND category = ? AND content = ?",
                (int(user_id), category, content),
            ).fetchone()
        persisted_id = str(row["id"] if row else memory_id)
        try:
            self._long_term_store.upsert(
                ids=[f"memory-{persisted_id}"],
                documents=[f"{category}：{content}"],
                metadatas=[
                    {
                        "memory_id": persisted_id,
                        "user_id": int(user_id),
                        "category": category,
                        "source": "long_term_memory",
                    }
                ],
            )
            self._memory_index_signature = ()
        except Exception:
            pass
        return {"category": category, "content": content, "importance": importance}

    def maybe_update_summary(
        self,
        session: Conversation,
        llm: Any | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> str | None:
        turn_count = int(session.state.get("turn_count", 0) or 0)
        if turn_count <= 0 or turn_count % max(1, self.summary_every_turns) != 0:
            return None

        existing = self.latest_summaries(session.user_id, session.id, limit=1)
        existing_summary = existing[0]["summary"] if existing else ""
        transcript = "\n".join(
            f"{message.get('role', '')}: {message.get('content', '')}"
            for message in self.recent_messages(session, self.short_term_turns)
        )
        summary = None
        if llm is not None:
            try:
                summary = llm.chat(
                    [
                        {
                            "role": "system",
                            "content": "你是健身对话总结器，输出可长期复用的用户目标、偏好、习惯、风险和注意事项。",
                        },
                        {
                            "role": "user",
                            "content": (
                                f"已有总结：{existing_summary or '无'}\n"
                                f"最新对话：\n{transcript}\n"
                                "请压缩成 120 字以内中文总结。"
                            ),
                        },
                    ],
                    provider,
                    model,
                    temperature=0,
                )
            except Exception:
                summary = None
        summary = (summary or self._fallback_summary(existing_summary, session.messages)).strip()
        if not summary:
            return None
        self._upsert_summary(session, summary)
        return summary

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

    def _upsert_summary(self, session: Conversation, summary: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        embedding = self.embeddings.embed_query(summary)
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO ai_memory_summaries(
                    id, user_id, session_id, summary, message_count,
                    embedding_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, session_id) DO UPDATE SET
                    summary = excluded.summary,
                    message_count = excluded.message_count,
                    embedding_json = excluded.embedding_json,
                    updated_at = excluded.updated_at
                """,
                (
                    str(uuid4()),
                    session.user_id,
                    session.id,
                    summary[:1000],
                    len(session.messages),
                    json.dumps(embedding, ensure_ascii=False),
                    now,
                    now,
                ),
            )
        try:
            self._summary_store.upsert(
                ids=[f"summary-{session.user_id}-{session.id}"],
                documents=[summary[:1000]],
                metadatas=[
                    {
                        "user_id": int(session.user_id),
                        "session_id": str(session.id),
                        "source": "memory_summary",
                    }
                ],
            )
        except Exception:
            pass

    def _parse_memory_items(self, raw: str) -> list[dict]:
        text = str(raw or "").strip()
        fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S | re.I)
        if fenced:
            text = fenced.group(1).strip()
        payload = json.loads(text)
        if isinstance(payload, dict):
            payload = payload.get("memories") or payload.get("items") or []
        if not isinstance(payload, list):
            return []
        result = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            category = self._normalize_category(item.get("category"))
            content = re.sub(r"\s+", " ", str(item.get("content") or "")).strip(" ;；。")
            if content:
                result.append(
                    {
                        "category": category,
                        "content": content[:300],
                        "importance": max(1, min(int(item.get("importance") or 3), 5)),
                    }
                )
        return result[:8]

    def _fallback_extract_memories(self, text: str) -> list[dict]:
        normalized = str(text or "").strip()
        if not normalized:
            return []
        memories: list[dict] = []

        age = re.search(r"(?:我)?(?:今年)?\s*(\d{1,3})\s*岁|年龄[:：]?\s*(\d{1,3})", normalized)
        if age:
            value = age.group(1) or age.group(2)
            memories.append({"category": "age", "content": f"年龄：{value}岁", "importance": 4})

        goal_patterns = [
            ("减脂", r"减脂|减肥|瘦身|降体脂|fat\s*loss|lose weight"),
            ("增肌", r"增肌|肌肉|力量提升|build muscle"),
            ("提升体能", r"提升体能|耐力|心肺|体能"),
            ("塑形", r"塑形|线条|身材"),
        ]
        for label, pattern in goal_patterns:
            if re.search(pattern, normalized, re.I):
                memories.append({"category": "goal", "content": f"目标：{label}", "importance": 4})

        body_patterns = [
            ("膝盖", r"膝盖|膝关节|knee"),
            ("腰部", r"腰疼|腰痛|腰不好|腰椎|lower back"),
            ("肩部", r"肩疼|肩痛|肩不好|shoulder"),
            ("脚踝", r"脚踝|踝关节|ankle"),
            ("手腕", r"手腕|腕关节|wrist"),
        ]
        for label, pattern in body_patterns:
            if re.search(pattern, normalized, re.I) and re.search(r"不好|疼|痛|伤|不舒服|受限|旧伤|problem|pain|injur", normalized, re.I):
                memories.append({"category": "body_issue", "content": f"身体问题：{label}不适", "importance": 5})

        habit_patterns = [
            ("晚上训练", r"晚上训练|夜间训练|下班后训练|晚饭后训练"),
            ("早上训练", r"早上训练|晨练|上午训练"),
            ("午间训练", r"中午训练|午休训练"),
        ]
        for label, pattern in habit_patterns:
            if re.search(pattern, normalized):
                memories.append({"category": "habit", "content": f"训练习惯：{label}", "importance": 3})

        preference_patterns = [
            ("低冲击训练", r"低冲击|不跳|少跳|low impact"),
            ("力量训练", r"力量训练|抗阻|撸铁|strength"),
            ("有氧训练", r"有氧|跑步|骑行|游泳|cardio"),
            ("居家训练", r"居家|在家练|徒手"),
        ]
        for label, pattern in preference_patterns:
            if re.search(pattern, normalized, re.I):
                memories.append({"category": "preference", "content": f"训练偏好：{label}", "importance": 3})

        deduped = {}
        for item in memories:
            deduped[(item["category"], item["content"])] = item
        return list(deduped.values())[:8]

    def _fallback_summary(self, existing_summary: str, messages: list[dict]) -> str:
        facts = []
        if existing_summary:
            facts.append(existing_summary)
        for message in messages[-20:]:
            if message.get("role") != "user":
                continue
            for item in self._fallback_extract_memories(str(message.get("content") or "")):
                facts.append(item["content"])
        deduped = []
        for fact in facts:
            if fact and fact not in deduped:
                deduped.append(fact)
        return "；".join(deduped)[:1000]

    def _memory_row(self, row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "user_id": row["user_id"],
            "category": row["category"],
            "content": row["content"],
            "source_session_id": row["source_session_id"],
            "importance": row["importance"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _normalize_category(self, value: Any) -> str:
        category = str(value or "other").strip().lower()
        aliases = {
            "injury": "body_issue",
            "injuries": "body_issue",
            "risk": "body_issue",
            "risk_flag": "body_issue",
            "health": "body_issue",
            "target": "goal",
            "goals": "goal",
            "preferred_time": "habit",
            "training_habit": "habit",
            "preferences": "preference",
        }
        category = aliases.get(category, category)
        allowed = {"age", "goal", "habit", "body_issue", "preference", "limitation", "other"}
        return category if category in allowed else "other"

    def _loads_vector(self, raw: str) -> list[float]:
        try:
            data = json.loads(raw or "[]")
            return [float(value) for value in data]
        except (TypeError, ValueError, json.JSONDecodeError):
            return []

    def _cosine(self, left: list[float], right: list[float]) -> float:
        if not left or not right:
            return 0.0
        size = min(len(left), len(right))
        return sum(left[index] * right[index] for index in range(size))

    def _distance_to_similarity(self, distance: Any) -> float:
        try:
            return max(0.0, min(1.0, 1.0 - float(distance)))
        except (TypeError, ValueError):
            return 0.0
