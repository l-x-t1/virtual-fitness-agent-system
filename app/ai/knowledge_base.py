from __future__ import annotations

import json
import re
from pathlib import Path
from threading import RLock
from uuid import uuid4

from app.agents.embedding_store import HashingEmbeddings


class FitnessKnowledgeBase:
    """Independent local fitness RAG index; never reads graph data."""

    def __init__(self, source: Path | None = None, custom_source: Path | None = None):
        self.source = source or Path(__file__).with_name("data") / "fitness_knowledge.json"
        self.custom_source = custom_source or self.source.with_name("fitness_knowledge_custom.json")
        self._lock = RLock()
        self.documents = self._load_documents()
        self.embeddings = HashingEmbeddings()
        self._store = None

    def _load_documents(self) -> list[dict]:
        documents = json.loads(self.source.read_text(encoding="utf-8"))
        if self.custom_source.exists():
            custom = json.loads(self.custom_source.read_text(encoding="utf-8"))
            documents.extend(custom if isinstance(custom, list) else [])
        deduplicated = {}
        for item in documents:
            deduplicated[str(item["id"])] = item
        return list(deduplicated.values())

    def _vector_store(self):
        if self._store is not None:
            return self._store
        try:
            from langchain_community.vectorstores import FAISS
            from langchain_core.documents import Document

            docs = [
                Document(page_content=f"{item['title']}：{item['content']}", metadata={"id": item["id"]})
                for item in self.documents
            ]
            self._store = FAISS.from_documents(docs, self.embeddings)
        except (ImportError, RuntimeError, ValueError):
            self._store = False
        return self._store

    def search(self, query: str, top_k: int = 3) -> list[dict]:
        store = self._vector_store()
        if store:
            hits = store.similarity_search_with_score(query, k=min(top_k, len(self.documents)))
            by_id = {item["id"]: item for item in self.documents}
            return [
                {**by_id[doc.metadata["id"]], "distance": round(float(distance), 4)}
                for doc, distance in hits
                if doc.metadata.get("id") in by_id
            ]
        return self._keyword_search(query, top_k)

    def vector_search(self, query: str, top_k: int = 3) -> list[dict]:
        """Use the existing FAISS index, with deterministic local cosine fallback."""
        store = self._vector_store()
        if store:
            hits = store.similarity_search_with_score(query, k=min(top_k, len(self.documents)))
            by_id = {item["id"]: item for item in self.documents}
            return [
                {
                    **by_id[doc.metadata["id"]],
                    "distance": round(float(distance), 6),
                    "similarity": round(1.0 / (1.0 + max(0.0, float(distance))), 6),
                    "vector_backend": "faiss",
                }
                for doc, distance in hits
                if doc.metadata.get("id") in by_id
            ]
        query_vector = self.embeddings.embed_query(query)
        ranked = []
        for item in self.documents:
            text = f"{item.get('title', '')}：{item.get('content', '')}"
            vector = self.embeddings.embed_query(text)
            similarity = sum(left * right for left, right in zip(query_vector, vector))
            ranked.append((max(0.0, similarity), item))
        ranked.sort(key=lambda pair: (-pair[0], str(pair[1].get("id", ""))))
        return [
            {
                **item,
                "distance": None,
                "similarity": round(score, 6),
                "vector_backend": "local-cosine",
            }
            for score, item in ranked[: min(max(1, top_k), len(ranked))]
        ]

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
            self._store = None
            return {"imported": len(imported), "total": len(self.documents), "documents": imported}

    def stats(self) -> dict:
        categories = {}
        for item in self.documents:
            category = item.get("category") or "general"
            categories[category] = categories.get(category, 0) + 1
        return {"total": len(self.documents), "categories": categories, "index": "FAISS + HashingEmbeddings"}

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
