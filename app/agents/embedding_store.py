from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings


class HashingEmbeddings(Embeddings):
    """Deterministic, dependency-free embeddings suitable for offline fallback."""

    def __init__(self, dimension: int = 384):
        self.dimension = dimension

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_query(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for token in self._tokens(text):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            vector[index] += 1.0 if digest[4] % 2 == 0 else -1.0
        norm = math.sqrt(sum(value * value for value in vector))
        return vector if not norm else [value / norm for value in vector]

    def _tokens(self, text: str) -> list[str]:
        lowered = text.lower()
        words = re.findall(r"[a-z0-9_]+", lowered)
        chinese = "".join(char for char in lowered if "\u4e00" <= char <= "\u9fff")
        chars = list(chinese)
        bigrams = [chinese[index:index + 2] for index in range(max(0, len(chinese) - 1))]
        return words + chars + bigrams


class ExerciseVectorStore:
    """In-memory semantic retrieval with FAISS and a deterministic local fallback."""

    def __init__(self, embeddings: Embeddings | None = None, prefer_faiss: bool = True):
        self.embeddings = embeddings or HashingEmbeddings()
        self.prefer_faiss = prefer_faiss
        self.last_backend = "uninitialized"

    def search(
        self,
        user: dict[str, Any],
        exercises: list[dict[str, Any]],
        exercise_name: str | None = None,
        top_k: int = 5,
        history: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        valid = [dict(item) for item in exercises if item.get("name")]
        if not valid or top_k <= 0:
            self.last_backend = "empty"
            return []
        query = self._query_text(user, exercise_name, history or [])
        documents = [self._document(item) for item in valid]
        if self.prefer_faiss:
            try:
                ranked = self._faiss_search(query, documents, valid, top_k)
                self.last_backend = "faiss"
                return ranked
            except Exception:
                # Import, native-library, and index-build failures all use the
                # deterministic implementation so offline behavior is testable.
                pass
        self.last_backend = "local"
        return self._local_search(query, documents, valid, top_k)

    def _faiss_search(
        self,
        query: str,
        documents: list[Document],
        exercises: list[dict[str, Any]],
        top_k: int,
    ) -> list[dict[str, Any]]:
        from langchain_community.vectorstores import FAISS

        store = FAISS.from_documents(documents, self.embeddings)
        results = store.similarity_search_with_score(query, k=min(top_k, len(documents)))
        by_name = {item["name"]: item for item in exercises}
        ranked = []
        for document, distance in results:
            name = document.metadata.get("name")
            if name not in by_name:
                continue
            similarity = max(0.0, 1.0 - float(distance) / 2.0)
            ranked.append(self._result(by_name[name], document, similarity, "faiss"))
        return ranked

    def _local_search(
        self,
        query: str,
        documents: list[Document],
        exercises: list[dict[str, Any]],
        top_k: int,
    ) -> list[dict[str, Any]]:
        query_vector = self.embeddings.embed_query(query)
        document_vectors = self.embeddings.embed_documents(
            [document.page_content for document in documents]
        )
        scored = []
        for item, document, vector in zip(exercises, documents, document_vectors):
            similarity = sum(left * right for left, right in zip(query_vector, vector))
            scored.append((similarity, item, document))
        scored.sort(key=lambda row: (-row[0], row[1]["name"]))
        return [
            self._result(item, document, max(0.0, similarity), "local")
            for similarity, item, document in scored[: min(top_k, len(scored))]
        ]

    def _result(
        self,
        item: dict[str, Any],
        document: Document,
        similarity: float,
        backend: str,
    ) -> dict[str, Any]:
        return {
            **item,
            "retrieval_score": round(min(100.0, similarity * 100.0), 1),
            "rag_score": round(min(100.0, similarity * 100.0), 1),
            "rag_context": document.page_content,
            "retrieval_backend": backend,
        }

    def _document(self, item: dict[str, Any]) -> Document:
        standard = item.get("standard")
        if standard is None:
            try:
                standard = json.loads(item.get("standard_json") or "{}")
            except (TypeError, json.JSONDecodeError):
                standard = {}
        content = "；".join(
            [
                f"动作：{item.get('name', '')}",
                f"类别：{item.get('category', '')}",
                f"难度：{item.get('difficulty', '')}",
                f"目标：{item.get('target', '')}",
                f"器材：{item.get('equipment', '')}",
                f"说明：{item.get('description', '')}",
                f"风险：{item.get('risk_warning', '')}",
                f"标准：{json.dumps(standard, ensure_ascii=False)}",
            ]
        )
        return Document(page_content=content, metadata={"name": item.get("name", "")})

    def _query_text(
        self,
        user: dict[str, Any],
        exercise_name: str | None,
        history: list[dict[str, Any]],
    ) -> str:
        goals = user.get("goals") or user.get("goal") or ""
        preferences = user.get("preferences") or user.get("preference") or ""
        parts = [
            f"体能水平：{user.get('fitness_level', '')}",
            f"训练目标：{goals}",
            f"运动偏好：{preferences}",
            f"伤病史：{user.get('injuries') or user.get('risk_flags') or '无'}",
            f"年龄：{user.get('age', '')}",
        ]
        if history:
            names = [str(item.get("exercise_name") or item.get("name") or "") for item in history[-10:]]
            parts.append("训练历史：" + "、".join(name for name in names if name))
        if exercise_name:
            parts.append(f"当前动作：{exercise_name}")
        return "；".join(parts)
