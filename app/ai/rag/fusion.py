from __future__ import annotations

import re
from collections import defaultdict

from app.ai.rag.schemas import EvidenceDocument


class ResultFusion:
    """Normalize, weight, fuse, and deduplicate heterogeneous retrieval results."""

    DEFAULT_WEIGHTS = {"bm25": 0.35, "vector": 0.40, "graph": 0.25}

    def __init__(self, weights: dict[str, float] | None = None):
        self.weights = {**self.DEFAULT_WEIGHTS, **(weights or {})}

    def fuse(self, routes: dict[str, list[EvidenceDocument]], top_k: int = 10) -> list[EvidenceDocument]:
        normalized = {
            route: self._normalize(items)
            for route, items in routes.items()
            if items
        }
        aggregated: dict[str, dict] = {}
        for route, items in normalized.items():
            weight = max(0.0, float(self.weights.get(route, 0.2)))
            for rank, (document, normalized_score) in enumerate(items, start=1):
                key = self._dedup_key(document)
                contribution = weight * (0.8 * normalized_score + 0.2 / rank)
                if key not in aggregated:
                    aggregated[key] = {
                        "document": document.model_copy(deep=True),
                        "score": 0.0,
                        "routes": [],
                        "route_scores": {},
                    }
                entry = aggregated[key]
                entry["score"] += contribution
                entry["routes"].append(route)
                entry["route_scores"][route] = round(normalized_score, 6)
                if len(document.content) > len(entry["document"].content):
                    entry["document"].content = document.content

        max_score = max((item["score"] for item in aggregated.values()), default=1.0) or 1.0
        fused = []
        for entry in aggregated.values():
            document = entry["document"]
            routes_used = sorted(set(entry["routes"]))
            document.source_type = "hybrid" if len(routes_used) > 1 else routes_used[0]
            document.score = round(min(1.0, entry["score"] / max_score), 6)
            document.metadata = {
                **document.metadata,
                "matched_source_types": routes_used,
                "route_scores": entry["route_scores"],
                "fusion_score_raw": round(entry["score"], 6),
            }
            fused.append(document)
        fused.sort(key=lambda item: (-item.score, item.source, item.title))
        return fused[: max(1, top_k)]

    def _normalize(self, items: list[EvidenceDocument]) -> list[tuple[EvidenceDocument, float]]:
        scores = [float(item.score) for item in items]
        low, high = min(scores), max(scores)
        output = []
        for rank, item in enumerate(items, start=1):
            if high > low:
                normalized = (float(item.score) - low) / (high - low)
            else:
                normalized = 1.0 / rank
            output.append((item, max(0.0, min(1.0, normalized))))
        return output

    def _dedup_key(self, document: EvidenceDocument) -> str:
        doc_id = document.metadata.get("id")
        if doc_id:
            return f"id:{doc_id}"
        if document.source:
            return f"source:{document.source.strip().lower()}"
        title = re.sub(r"\W+", "", document.title.lower())
        content = re.sub(r"\W+", "", document.content.lower())[:160]
        return f"text:{title}:{content}"
