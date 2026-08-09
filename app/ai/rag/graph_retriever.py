from __future__ import annotations

import json
from typing import Any, Callable

from app.ai.rag.schemas import EvidenceDocument


class GraphRetriever:
    """Read-only adapter for GraphService; unavailable graph means no documents."""

    def __init__(self, service_factory: Callable[[], Any] | None = None):
        self.service_factory = service_factory or self._default_service
        self.last_error: str | None = None

    def retrieve(self, query: str, user_id: int | None = None, top_k: int = 5) -> list[EvidenceDocument]:
        self.last_error = None
        try:
            service = self.service_factory()
            status = service.status()
            if not bool(getattr(status, "available", False)):
                self.last_error = "neo4j_unavailable"
                return []
            result = service.search(query, user_id=user_id, top_k=top_k, use_llm=False)
            payload = result.model_dump() if hasattr(result, "model_dump") else dict(result)
            return self._documents(payload, top_k)
        except Exception:
            self.last_error = "graph_retrieval_failed"
            return []

    def _documents(self, payload: dict[str, Any], top_k: int) -> list[EvidenceDocument]:
        output = []
        for kind, items in (("knowledge", payload.get("knowledge", [])), ("relation", payload.get("relations", []))):
            for index, raw in enumerate(items or []):
                item = raw if isinstance(raw, dict) else {"value": raw}
                title = str(item.get("title") or item.get("name") or item.get("type") or f"图谱{kind}")
                content = str(
                    item.get("content")
                    or item.get("description")
                    or item.get("text")
                    or json.dumps(item, ensure_ascii=False, default=str)
                )
                source_id = item.get("id") or item.get("element_id") or f"{kind}-{index}"
                raw_score = item.get("score", item.get("similarity", 0.6))
                try:
                    score = max(0.0, min(1.0, float(raw_score)))
                except (TypeError, ValueError):
                    score = 0.6
                output.append(
                    EvidenceDocument(
                        source=f"graph:{source_id}",
                        source_type="graph",
                        title=title,
                        content=content,
                        score=score,
                        metadata={"graph_kind": kind, **item},
                    )
                )
        return output[: max(1, top_k)]

    def _default_service(self):
        from app.services.graph_service import get_graph_service

        return get_graph_service()
