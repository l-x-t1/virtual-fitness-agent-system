from __future__ import annotations

from typing import Any

from app.ai.rag.schemas import EvidenceDocument


class VectorRetriever:
    """Adapter over the existing FitnessKnowledgeBase FAISS/local vector index."""

    def __init__(self, knowledge_base: Any):
        self.knowledge_base = knowledge_base
        self.backend = "unknown"

    def retrieve(self, query: str, top_k: int = 5) -> list[EvidenceDocument]:
        hits = self.knowledge_base.vector_search(query, top_k=top_k)
        documents = []
        for index, item in enumerate(hits):
            self.backend = str(item.get("vector_backend") or "unknown")
            documents.append(
                EvidenceDocument(
                    source=f"knowledge:{item.get('id', index)}",
                    source_type="vector",
                    title=str(item.get("title") or item.get("id") or "健身资料"),
                    content=str(item.get("content") or ""),
                    score=max(0.0, min(1.0, float(item.get("similarity") or 0.0))),
                    metadata={
                        "id": str(item.get("id", index)),
                        "category": item.get("category", "general"),
                        "retrieval_backend": self.backend,
                        "distance": item.get("distance"),
                    },
                )
            )
        return documents
