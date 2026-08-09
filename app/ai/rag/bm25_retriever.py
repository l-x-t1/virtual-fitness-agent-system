from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

from app.ai.rag.schemas import EvidenceDocument


def tokenize_zh(text: str) -> list[str]:
    lowered = str(text or "").lower()
    words = re.findall(r"[a-z0-9]+", lowered)
    chunks = re.findall(r"[\u4e00-\u9fff]+", lowered)
    chars = [char for chunk in chunks for char in chunk]
    bigrams = [chunk[index : index + 2] for chunk in chunks for index in range(max(0, len(chunk) - 1))]
    return words + chars + bigrams


class BM25Retriever:
    """BM25 retriever with a deterministic Chinese keyword fallback."""

    def __init__(self, documents: list[dict[str, Any]]):
        self.documents = list(documents)
        self._corpus = [tokenize_zh(self._text(item)) for item in self.documents]
        self._bm25 = self._build_bm25()
        self.backend = "rank-bm25" if self._bm25 is not None else "local-keyword"

    def retrieve(self, query: str, top_k: int = 5) -> list[EvidenceDocument]:
        tokens = tokenize_zh(query)
        if not self.documents or not tokens:
            return []
        scores = self._scores(tokens)
        ranked = sorted(enumerate(scores), key=lambda pair: (-pair[1], pair[0]))
        hits = []
        for index, score in ranked[: min(max(1, top_k), len(ranked))]:
            if score <= 0 and hits:
                continue
            item = self.documents[index]
            hits.append(
                EvidenceDocument(
                    source=f"knowledge:{item.get('id', index)}",
                    source_type="bm25",
                    title=str(item.get("title") or item.get("id") or "健身资料"),
                    content=str(item.get("content") or ""),
                    score=self._bounded_score(score),
                    metadata={
                        "id": str(item.get("id", index)),
                        "category": item.get("category", "general"),
                        "retrieval_backend": self.backend,
                        "raw_score": round(float(score), 6),
                    },
                )
            )
        return hits

    def _build_bm25(self):
        try:
            from rank_bm25 import BM25Okapi

            return BM25Okapi(self._corpus)
        except (ImportError, ValueError, ZeroDivisionError):
            return None

    def _scores(self, query_tokens: list[str]) -> list[float]:
        if self._bm25 is not None:
            return [float(value) for value in self._bm25.get_scores(query_tokens)]
        query_counts = Counter(query_tokens)
        document_frequency = Counter(token for tokens in self._corpus for token in set(tokens))
        total = max(1, len(self._corpus))
        scores = []
        for tokens in self._corpus:
            counts = Counter(tokens)
            score = 0.0
            for token, query_count in query_counts.items():
                if not counts[token]:
                    continue
                idf = math.log(1 + (total - document_frequency[token] + 0.5) / (document_frequency[token] + 0.5))
                score += idf * min(counts[token], 3) * min(query_count, 2)
            scores.append(score)
        return scores

    def _bounded_score(self, score: float) -> float:
        return round(max(0.0, min(1.0, 1.0 - math.exp(-max(0.0, score)))), 6)

    def _text(self, item: dict[str, Any]) -> str:
        return f"{item.get('title', '')} {item.get('category', '')} {item.get('content', '')}"
