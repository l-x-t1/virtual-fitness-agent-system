from __future__ import annotations

import json
import re
from pathlib import Path
from threading import RLock
from uuid import uuid4

from app.embeddings import SemanticEmbeddings
from app.vectorstore import ChromaVectorStore


class FitnessKnowledgeBase:
    """Independent local fitness RAG index backed by persistent Chroma."""

    def __init__(
        self,
        source: Path | None = None,
        custom_source: Path | None = None,
        *,
        embeddings: SemanticEmbeddings | None = None,
        persist_directory: str | Path | None = None,
    ):
        self.source = source or Path(__file__).with_name("data") / "fitness_knowledge.json"
        self.custom_source = custom_source or self.source.with_name("fitness_knowledge_custom.json")
        self._lock = RLock()
        self.documents = self._load_documents()
        self.embeddings = embeddings or SemanticEmbeddings()
        self._store = ChromaVectorStore(
            collection_name="fitness-knowledge",
            embeddings=self.embeddings,
            persist_directory=persist_directory,
        )
        self._indexed_signature: tuple[str, ...] = ()
        self._vector_available = True

    def _load_documents(self) -> list[dict]:
        documents = json.loads(self.source.read_text(encoding="utf-8"))
        if self.custom_source.exists():
            custom = json.loads(self.custom_source.read_text(encoding="utf-8"))
            documents.extend(custom if isinstance(custom, list) else [])
        deduplicated = {}
        for item in documents:
            deduplicated[str(item["id"])] = item
        return list(deduplicated.values())

    def _ensure_vector_index(self) -> bool:
        signature = tuple(
            sorted(
                "|".join(
                    [
                        str(item.get("id", "")),
                        str(item.get("title", "")),
                        str(item.get("category", "")),
                        str(item.get("content", "")),
                    ]
                )
                for item in self.documents
            )
        )
        if self._indexed_signature == signature and self._vector_available:
            return True
        try:
            ids = [self._id_for(item) for item in self.documents]
            docs = [self._document_text(item) for item in self.documents]
            metadatas = [
                {
                    "id": str(item["id"]),
                    "category": str(item.get("category") or "general"),
                    "source": "fitness_knowledge",
                }
                for item in self.documents
            ]
            self._store.upsert(ids=ids, documents=docs, metadatas=metadatas)
            self._indexed_signature = signature
            self._vector_available = True
            return True
        except Exception:
            self._vector_available = False
            return False

    def search(self, query: str, top_k: int = 3) -> list[dict]:
        return self.vector_search(query, top_k=top_k) or self._keyword_search(query, top_k)

    def vector_search(self, query: str, top_k: int = 3) -> list[dict]:
        """Search the persistent Chroma index; fall back to semantic cosine in memory."""
        if self._ensure_vector_index():
            by_id = {str(item["id"]): item for item in self.documents}
            hits = self._store.query(
                query,
                n_results=min(max(1, top_k), len(self.documents)),
                where={"source": "fitness_knowledge"},
            )
            results = []
            for hit in hits:
                metadata = hit.get("metadata") or {}
                doc_id = str(metadata.get("id") or "").strip()
                if doc_id not in by_id:
                    continue
                similarity = self._distance_to_similarity(hit.get("distance"))
                results.append(
                    {
                        **by_id[doc_id],
                        "distance": hit.get("distance"),
                        "similarity": round(similarity, 6),
                        "vector_backend": "chroma",
                    }
                )
            if results:
                return results
        return self._local_semantic_search(query, top_k)

    def import_documents(self, documents: list[dict]) -> dict:
        with self._lock:
            existing_custom = []
            if self.custom_source.exists():
                payload = json.loads(self.custom_source.read_text(encoding="utf-8"))
                existing_custom = payload if isinstance(payload, list) else []
            by_id = {str(item["id"]): item for item in existing_custom}
            imported = []
            for raw in documents:
                title = str(raw.get("title") or "").strip()
                content = str(raw.get("content") or "").strip()
                if not title or not content:
                    continue
                doc_id = str(raw.get("id") or f"custom-{uuid4().hex[:12]}")
                item = {
                    "id": doc_id,
                    "title": title[:200],
                    "content": content[:10000],
                    "category": str(raw.get("category") or "custom")[:50],
                }
                by_id[doc_id] = item
                imported.append(item)
            self.custom_source.write_text(
                json.dumps(list(by_id.values()), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self.documents = self._load_documents()
            self._indexed_signature = ()
            self._ensure_vector_index()
            return {"imported": len(imported), "total": len(self.documents), "documents": imported}

    def stats(self) -> dict:
        categories = {}
        for item in self.documents:
            category = item.get("category") or "general"
            categories[category] = categories.get(category, 0) + 1
        return {
            "total": len(self.documents),
            "categories": categories,
            "index": "Chroma + SemanticEmbeddings",
            "embedding_model": self.embeddings.model_name,
            "embedding_backend": self.embeddings.backend,
        }

    def _local_semantic_search(self, query: str, top_k: int) -> list[dict]:
        query_vector = self.embeddings.embed_query(query)
        doc_vectors = self.embeddings.embed_documents(
            [self._document_text(item) for item in self.documents]
        )
        ranked = []
        for item, vector in zip(self.documents, doc_vectors):
            similarity = self._cosine(query_vector, vector)
            ranked.append((similarity, item))
        ranked.sort(key=lambda pair: (-pair[0], str(pair[1].get("id", ""))))
        return [
            {
                **item,
                "distance": None,
                "similarity": round(score, 6),
                "vector_backend": "local",
            }
            for score, item in ranked[: min(max(1, top_k), len(ranked))]
        ]

    def _keyword_search(self, query: str, top_k: int) -> list[dict]:
        tokens = set(re.findall(r"[\u4e00-\u9fff]|[a-z0-9]+", query.lower()))
        ranked = []
        for item in self.documents:
            text = f"{item['title']}{item['content']}".lower()
            score = sum(1 for token in tokens if token in text)
            ranked.append((score, item))
        ranked.sort(key=lambda pair: pair[0], reverse=True)
        return [{**item, "distance": None} for score, item in ranked[:top_k] if score > 0] or [
            {**item, "distance": None} for _, item in ranked[:top_k]
        ]

    def _id_for(self, item: dict) -> str:
        return f"knowledge-{item['id']}"

    def _document_text(self, item: dict) -> str:
        return "\n".join(
            [
                f"标题：{item.get('title', '')}",
                f"分类：{item.get('category', 'general')}",
                f"内容：{item.get('content', '')}",
            ]
        )

    def _distance_to_similarity(self, distance) -> float:
        try:
            return max(0.0, min(1.0, 1.0 - float(distance)))
        except (TypeError, ValueError):
            return 0.0

    def _cosine(self, left: list[float], right: list[float]) -> float:
        size = min(len(left), len(right))
        return max(0.0, sum(left[index] * right[index] for index in range(size)))
