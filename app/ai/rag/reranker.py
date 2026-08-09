from __future__ import annotations

import json
from typing import Any, Callable

from app.ai.rag.bm25_retriever import tokenize_zh
from app.ai.rag.schemas import EvidenceDocument, RerankResult
from app.agents.output_parser import OutputParser


class EvidenceReranker:
    """Optional custom/LLM reranker with deterministic evidence-only fallback."""

    def __init__(self, llm: Any | None = None, reranker: Callable[..., Any] | None = None):
        self.llm = llm
        self.reranker = reranker
        self.parser = OutputParser()

    def rerank(
        self,
        query: str,
        documents: list[EvidenceDocument],
        memory_text: str = "",
        top_k: int = 5,
        provider: str | None = None,
        model: str | None = None,
    ) -> RerankResult:
        if not documents:
            return RerankResult(documents=[], mode="fallback", fallback_reason="no_evidence")
        if self.reranker is not None:
            try:
                ranked = self.reranker(query, documents, top_k=top_k)
                validated = self._validate_external(ranked, documents, top_k)
                if validated:
                    return RerankResult(documents=validated, mode="reranker")
            except Exception:
                pass
        if self.llm is not None:
            try:
                ranked = self._llm_rerank(query, documents, memory_text, top_k, provider, model)
                if ranked:
                    return RerankResult(documents=ranked, mode="online")
            except Exception:
                pass
        return RerankResult(
            documents=self._local_rerank(query, documents, memory_text, top_k),
            mode="fallback",
            fallback_reason="model_unavailable_or_invalid",
        )

    def _llm_rerank(self, query, documents, memory_text, top_k, provider, model):
        candidates = [
            {
                "source": item.source,
                "title": item.title,
                "content": item.content[:700],
                "fusion_score": item.score,
            }
            for item in documents[:12]
        ]
        prompt = (
            "只根据问题、用户记忆和候选证据重排。不得新增 source。"
            '返回 JSON：{"ranking":[{"source":"...","score":0.0}]}。\n'
            f"问题：{query}\n用户记忆：{memory_text[:800]}\n"
            f"候选：{json.dumps(candidates, ensure_ascii=False)}"
        )
        raw = self.llm.chat(
            [{"role": "system", "content": "你是证据相关性重排器，只返回 JSON。"}, {"role": "user", "content": prompt}],
            provider,
            model,
            temperature=0,
        )
        payload = self.parser.loads(raw)
        allowed = {item.source: item for item in documents}
        output = []
        used = set()
        for row in payload.get("ranking", []):
            source = str(row.get("source") or "")
            if source not in allowed or source in used:
                continue
            item = allowed[source].model_copy(deep=True)
            item.score = max(0.0, min(1.0, float(row.get("score", item.score))))
            item.metadata["rerank_mode"] = "llm"
            output.append(item)
            used.add(source)
        output.extend(item for item in documents if item.source not in used)
        return output[: max(1, top_k)]

    def _local_rerank(self, query, documents, memory_text, top_k):
        query_tokens = set(tokenize_zh(f"{query} {memory_text}"))
        scored = []
        for item in documents:
            doc_tokens = set(tokenize_zh(f"{item.title} {item.content}"))
            overlap = len(query_tokens & doc_tokens) / max(1, len(query_tokens))
            score = 0.65 * float(item.score) + 0.35 * overlap
            copy = item.model_copy(deep=True)
            copy.score = round(max(0.0, min(1.0, score)), 6)
            copy.metadata["rerank_mode"] = "local"
            copy.metadata["token_overlap"] = round(overlap, 6)
            scored.append(copy)
        scored.sort(key=lambda item: (-item.score, item.source, item.title))
        return scored[: max(1, top_k)]

    def _validate_external(self, ranked, originals, top_k):
        allowed = {item.source: item for item in originals}
        output = []
        for raw in ranked or []:
            item = raw if isinstance(raw, EvidenceDocument) else EvidenceDocument.model_validate(raw)
            if item.source in allowed:
                output.append(item)
        return output[: max(1, top_k)]
