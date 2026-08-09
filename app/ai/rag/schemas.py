from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class EvidenceDocument(BaseModel):
    source: str
    source_type: str
    title: str
    content: str
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RewriteResult(BaseModel):
    original_query: str
    queries: list[str] = Field(default_factory=list)
    mode: str = "fallback"
    fallback_reason: str | None = None


class RerankResult(BaseModel):
    documents: list[EvidenceDocument] = Field(default_factory=list)
    mode: str = "fallback"
    fallback_reason: str | None = None


class RAGResult(BaseModel):
    answer: str
    mode: str
    original_query: str
    rewritten_queries: list[str]
    evidence: list[EvidenceDocument] = Field(default_factory=list)
    sources: list[dict[str, Any]] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    retrieval_counts: dict[str, int] = Field(default_factory=dict)
    rewrite_mode: str
    rerank_mode: str
    trace_id: str
    fallback_reason: str | None = None
