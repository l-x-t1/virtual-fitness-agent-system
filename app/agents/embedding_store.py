from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings


class HashingEmbeddings(Embeddings):
    """Small local embedding model that implements LangChain's Embeddings interface."""

    def __init__(self, dimension: int = 384):
        self.dimension = dimension

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_query(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for token in self._tokens(text):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if not norm:
            return vector
        return [value / norm for value in vector]

    def _tokens(self, text: str) -> list[str]:
        lowered = text.lower()
        words = re.findall(r"[a-z0-9_]+", lowered)
        chars = [char for char in lowered if "\u4e00" <= char <= "\u9fff"]
        bigrams = [lowered[index:index + 2] for index in range(max(0, len(lowered) - 1))]
        return words + chars + bigrams


class ExerciseVectorStore:
    """Build an in-memory FAISS index for exercise RAG candidates."""

    def __init__(self, embeddings: Embeddings | None = None):
        self.embeddings = embeddings or HashingEmbeddings()

    def search(self, user: dict[str, Any], exercises: list[dict[str, Any]], exercise_name: str | None = None,
               top_k: int = 5) -> list[dict[str, Any]]:
        if not exercises:
            return []

        try:
            from langchain_community.vectorstores import FAISS
        except ImportError as exc:
            raise RuntimeError("langchain-community and faiss-cpu are required for FAISS retrieval.") from exc

        documents = [self._document(item) for item in exercises]
        store = FAISS.from_documents(documents, self.embeddings)
        query = self._query_text(user, exercise_name)
        results = store.similarity_search_with_score(query, k=min(top_k, len(documents)))
        ranked = []
        by_name = {item.get("name"): item for item in exercises}
        for document, distance in results:
            name = document.metadata.get("name")
            if name not in by_name:
                continue
            item = dict(by_name[name])
            item["rag_score"] = round(max(0.0, 100.0 - float(distance) * 20.0), 1)
            item["rag_context"] = document.page_content
            ranked.append(item)
        return ranked

    def _document(self, item: dict[str, Any]) -> Document:
        standard = item.get("standard")
        if standard is None:
            try:
                standard = json.loads(item.get("standard_json") or "{}")
            except (TypeError, json.JSONDecodeError):
                standard = {}
        content = "；".join([
            f"动作：{item.get('name', '')}",
            f"类别：{item.get('category', '')}",
            f"难度：{item.get('difficulty', '')}",
            f"目标：{item.get('target', '')}",
            f"器材：{item.get('equipment', '')}",
            f"标准：{json.dumps(standard, ensure_ascii=False)}",
        ])
        return Document(page_content=content, metadata={"name": item.get("name", "")})

    def _query_text(self, user: dict[str, Any], exercise_name: str | None) -> str:
        parts = [
            f"体能水平：{user.get('fitness_level', '')}",
            f"运动偏好：{user.get('preference', '')}",
            f"伤病史：{user.get('injuries') or '无'}",
            f"年龄：{user.get('age', '')}",
        ]
        if exercise_name:
            parts.append(f"当前动作：{exercise_name}")
        return "；".join(parts)
