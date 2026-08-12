from __future__ import annotations

import json
import os
from typing import Any

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from app.embeddings import SemanticEmbeddings
from app.vectorstore import ChromaVectorStore


class ExerciseVectorStore:
    """Semantic exercise retrieval backed by persistent Chroma.

    ``prefer_faiss`` remains accepted for compatibility with older callers, but
    FAISS is no longer used.  If Chroma is unavailable, the same semantic
    embeddings are ranked in memory as an explicit local fallback.
    """

    def __init__(
        self,
        embeddings: Embeddings | None = None,
        prefer_faiss: bool | None = None,
        *,
        persist_directory: str | None = None,
        collection_name: str | None = None,
    ):
        self.embeddings = embeddings or SemanticEmbeddings()
        self.persist_directory = persist_directory
        self.collection_name = collection_name or os.getenv(
            "EXERCISE_CHROMA_COLLECTION", "fitness-exercises"
        )
        self.vector_store = ChromaVectorStore(
            collection_name=self.collection_name,
            embeddings=self.embeddings,
            persist_directory=persist_directory,
        )
        self.last_backend = "uninitialized"
        self.last_error: str | None = None
        self._indexed_ids: set[str] = set()

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
        try:
            self._sync_chroma(valid, documents)
            results = self.vector_store.query(
                query,
                n_results=min(top_k, len(valid)),
                where={"source": "exercise"},
            )
            by_id = {self._id_for(item): item for item in valid}
            ranked = []
            for result in results:
                item = by_id.get(str(result["id"]))
                if item is None:
                    continue
                similarity = self._distance_to_similarity(result.get("distance"))
                document = Document(
                    page_content=str(result.get("document") or ""),
                    metadata=result.get("metadata") or {},
                )
                ranked.append(self._result(item, document, similarity, "chroma"))
            if ranked:
                self.last_backend = "chroma"
                self.last_error = None
                return ranked
        except Exception as exc:
            self.last_error = str(exc)

        self.last_backend = "local-semantic"
        return self._local_search(query, documents, valid, top_k)

    def _sync_chroma(self, exercises: list[dict[str, Any]], documents: list[Document]) -> None:
        ids = [self._id_for(item) for item in exercises]
        current_ids = set(ids)
        stale_ids = self._indexed_ids - current_ids
        if stale_ids:
            self.vector_store.delete(ids=sorted(stale_ids))
        self.vector_store.upsert(
            ids=ids,
            documents=[document.page_content for document in documents],
            metadatas=[
                {"name": item["name"], "source": "exercise", "category": str(item.get("category") or "")}
                for item in exercises
            ],
        )
        self._indexed_ids = current_ids

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
            similarity = self._cosine(query_vector, vector)
            scored.append((similarity, item, document))
        scored.sort(key=lambda row: (-row[0], row[1]["name"]))
        return [
            self._result(item, document, max(0.0, similarity), "local-semantic")
            for similarity, item, document in scored[: min(top_k, len(scored))]
        ]

    def _result(
        self,
        item: dict[str, Any],
        document: Document,
        similarity: float,
        backend: str,
    ) -> dict[str, Any]:
        score = round(min(100.0, max(0.0, similarity) * 100.0), 1)
        return {
            **item,
            "retrieval_score": score,
            "rag_score": score,
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
        content = "\n".join(
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
            names = [
                str(item.get("exercise_name") or item.get("name") or "")
                for item in history[-10:]
            ]
            parts.append("训练历史：" + "、".join(name for name in names if name))
        if exercise_name:
            parts.append(f"当前动作：{exercise_name}")
        return "\n".join(parts)

    def _id_for(self, item: dict[str, Any]) -> str:
        return f"exercise-{item.get('id') or item.get('name')}"

    def _distance_to_similarity(self, distance: Any) -> float:
        try:
            return max(0.0, min(1.0, 1.0 - float(distance)))
        except (TypeError, ValueError):
            return 0.0

    def _cosine(self, left: list[float], right: list[float]) -> float:
        size = min(len(left), len(right))
        return max(0.0, sum(left[index] * right[index] for index in range(size)))
