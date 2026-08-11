from __future__ import annotations

import json
import re
import time
from typing import Any

from app.ai.knowledge_base import FitnessKnowledgeBase
from app.ai.rag.bm25_retriever import BM25Retriever
from app.ai.rag.fusion import ResultFusion
from app.ai.rag.graph_retriever import GraphRetriever
from app.ai.rag.query_rewriter import QueryRewriter
from app.ai.rag.reranker import EvidenceReranker
from app.ai.rag.schemas import EvidenceDocument, RAGResult
from app.ai.rag.vector_retriever import VectorRetriever
from app.llm import LLMClient, LLMError
from app.observability import TraceContext, get_tracer


class HybridRAGPipeline:
    """Query rewrite -> BM25/vector/graph -> fusion -> rerank -> grounded answer."""

    def __init__(
        self,
        knowledge_base: FitnessKnowledgeBase | None = None,
        llm: Any | None = None,
        graph_retriever: GraphRetriever | None = None,
        tracer: Any | None = None,
    ):
        self.knowledge_base = knowledge_base or FitnessKnowledgeBase()
        self.llm = llm or LLMClient()
        self.query_rewriter = QueryRewriter(self.llm)
        self.bm25 = BM25Retriever(self.knowledge_base.documents)
        self.vector = VectorRetriever(self.knowledge_base)
        self.graph = graph_retriever or GraphRetriever()
        self.fusion = ResultFusion()
        self.reranker = EvidenceReranker(self.llm)
        self.tracer = tracer or get_tracer()

    def retrieve(
        self,
        question: str,
        *,
        recent_messages: list[dict[str, Any]] | None = None,
        memory: Any | None = None,
        user_id: int | None = None,
        provider: str | None = None,
        model: str | None = None,
        top_k: int = 5,
        trace: TraceContext | None = None,
    ) -> dict[str, Any]:
        active_trace = trace or self.tracer.start_trace("hybrid_rag", user_id=user_id)
        memory_text = self._memory_text(memory)
        with active_trace.span("rag.query_rewrite", prompt_template="hybrid_rag_query_rewrite"):
            rewritten = self.query_rewriter.rewrite(
                question, recent_messages, memory, provider=provider, model=model
            )
        routes: dict[str, list[EvidenceDocument]] = {"bm25": [], "vector": [], "graph": []}
        with active_trace.span("rag.retrieve", queries=rewritten.queries):
            for query in rewritten.queries:
                routes["bm25"].extend(self.bm25.retrieve(query, top_k=max(top_k, 5)))
                routes["vector"].extend(self.vector.retrieve(query, top_k=max(top_k, 5)))
            routes["graph"] = self.graph.retrieve(
                rewritten.queries[0] if rewritten.queries else question,
                user_id=user_id,
                top_k=max(top_k, 5),
            )
        routes = {name: self._dedup_route(items) for name, items in routes.items()}
        counts = {name: len(items) for name, items in routes.items()}
        with active_trace.span("rag.fusion", retrieval_counts=counts):
            fused = self.fusion.fuse(routes, top_k=max(top_k * 2, 8))
        with active_trace.span("rag.rerank", candidate_count=len(fused)):
            reranked = self.reranker.rerank(
                question,
                fused,
                memory_text=memory_text,
                top_k=top_k,
                provider=provider,
                model=model,
            )
        active_trace.event(
            "rag.result",
            {
                "retrieval_counts": counts,
                "rewrite_mode": rewritten.mode,
                "rerank_mode": reranked.mode,
                "rerank_results": [
                    {"source": item.source, "score": item.score}
                    for item in reranked.documents
                ],
                "graph_fallback": self.graph.last_error,
            },
        )
        return {
            "rewrite": rewritten,
            "routes": routes,
            "retrieval_counts": counts,
            "evidence": reranked.documents,
            "rerank_mode": reranked.mode,
            "rerank_fallback_reason": reranked.fallback_reason,
            "trace": active_trace,
            "memory_text": memory_text,
        }

    def run(
        self,
        question: str,
        *,
        recent_messages: list[dict[str, Any]] | None = None,
        memory: Any | None = None,
        user_id: int | None = None,
        session_id: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        top_k: int = 5,
        trace: TraceContext | None = None,
    ) -> RAGResult:
        active_trace = trace or self.tracer.start_trace(
            "hybrid_rag", session_id=session_id, user_id=user_id
        )
        retrieval = self.retrieve(
            question,
            recent_messages=recent_messages,
            memory=memory,
            user_id=user_id,
            provider=provider,
            model=model,
            top_k=top_k,
            trace=active_trace,
        )
        return self.complete(
            question,
            retrieval,
            provider=provider,
            model=model,
            trace=active_trace,
        )

    def complete(
        self,
        question: str,
        retrieval: dict[str, Any],
        *,
        provider: str | None = None,
        model: str | None = None,
        trace: TraceContext | None = None,
        answer_override: str | None = None,
        mode_override: str | None = None,
        finish_trace: bool = True,
    ) -> RAGResult:
        active_trace = trace or retrieval.get("trace") or self.tracer.start_trace("hybrid_rag")
        evidence = retrieval["evidence"]
        started = time.perf_counter()
        if answer_override is not None:
            answer = self._safety_note(
                f"{question} {retrieval['memory_text']}", answer_override.strip()
            )
            mode = mode_override or "online"
            fallback_reason = None if mode == "online" else "stream_fallback"
        else:
            try:
                answer = self._online_answer(
                    question, evidence, retrieval["memory_text"], provider, model
                )
                mode = "online"
                fallback_reason = None
            except (LLMError, ValueError, TypeError, KeyError):
                answer = self._fallback_answer(question, evidence, retrieval["memory_text"])
                mode = "fallback"
                fallback_reason = "llm_unavailable_or_invalid"
        elapsed = (time.perf_counter() - started) * 1000
        active_trace.event(
            "llm.answer",
            {
                "provider": self._provider_name(provider),
                "model": self._model_name(model),
                "input_tokens": self._estimate_tokens(question + retrieval["memory_text"] + self._evidence_text(evidence)),
                "output_tokens": self._estimate_tokens(answer),
                "latency_ms": round(elapsed, 3),
                "first_token_latency_ms": round(elapsed, 3),
                "mode": mode,
                "fallback_reason": fallback_reason,
            },
        )
        sources = [self._source(item, index) for index, item in enumerate(evidence, start=1)]
        citations = [f"[{index}]" for index in range(1, len(sources) + 1)]
        result = RAGResult(
            answer=answer,
            mode=mode,
            original_query=question,
            rewritten_queries=retrieval["rewrite"].queries,
            evidence=evidence,
            sources=sources,
            citations=citations,
            retrieval_counts=retrieval["retrieval_counts"],
            rewrite_mode=retrieval["rewrite"].mode,
            rerank_mode=retrieval["rerank_mode"],
            trace_id=active_trace.trace_id,
            fallback_reason=fallback_reason,
        )
        if finish_trace:
            active_trace.finish({"mode": mode, "source_count": len(sources)})
        return result

    def answer_messages(
        self,
        question: str,
        retrieval: dict[str, Any],
    ) -> list[dict[str, str]]:
        evidence = retrieval.get("evidence") or []
        prompt = self._grounded_prompt(
            question, evidence, str(retrieval.get("memory_text") or "")
        )
        return [
            {"role": "system", "content": "你是严格基于证据的健身助手。"},
            {"role": "user", "content": prompt},
        ]

    def _online_answer(self, question, evidence, memory_text, provider, model):
        if not evidence:
            raise ValueError("no evidence")
        prompt = self._grounded_prompt(question, evidence, memory_text)
        answer = self.llm.chat(
            [
                {"role": "system", "content": "你是严格基于证据的健身助手。"},
                {"role": "user", "content": prompt},
            ],
            provider,
            model,
            temperature=0.2,
        ).strip()
        if not answer:
            raise ValueError("empty answer")
        return self._safety_note(f"{question} {memory_text}", answer)

    def _grounded_prompt(self, question, evidence, memory_text):
        return (
            "你只能依据下方编号证据和用户记忆回答。每个事实在句末标注 [编号]。"
            "证据不足时明确说不确定；不得编造资料或图谱关系。"
            "涉及伤病或疼痛时加入安全提示，并说明不能替代医生诊断。\n"
            f"问题：{question}\n用户记忆：{memory_text[:1200]}\n证据：\n{self._evidence_text(evidence)}"
        )

    def _fallback_answer(self, question, evidence, memory_text):
        if not evidence:
            answer = "当前知识库和可用图谱中没有找到足够证据，因此暂时无法给出确定回答。"
        else:
            lines = ["根据当前召回证据："]
            for index, item in enumerate(evidence[:3], start=1):
                lines.append(f"{index}. {item.title}：{item.content} [{index}]")
            if memory_text:
                constraints = self._memory_constraints(memory_text)
                if constraints:
                    lines.append(f"已结合用户保存的相关约束：{'；'.join(constraints)}。")
                lines.append("用户记忆仅用于个性化，不会作为知识库事实或医疗诊断。")
            answer = "\n".join(lines)
        return self._safety_note(f"{question} {memory_text}", answer)

    def _memory_constraints(self, memory_text: str) -> list[str]:
        constraints = []
        for line in str(memory_text or "").splitlines():
            value = line.strip().lstrip("- ").strip()
            if not value or value.startswith(("以下是", "【")):
                continue
            constraints.append(value[:160])
        return list(dict.fromkeys(constraints))[:3]

    def _safety_note(self, question: str, answer: str) -> str:
        if re.search(r"痛|疼|伤|膝|腰|踝|胸闷|晕|呼吸困难", question):
            return answer + "\n安全提示：以上内容不能替代医生诊断；若出现急性剧痛、胸痛、晕厥或异常呼吸困难，请立即停止运动并及时就医。"
        return answer

    def _source(self, item: EvidenceDocument, index: int) -> dict[str, Any]:
        return {
            "citation": f"[{index}]",
            "id": item.source,
            "source": item.source,
            "source_type": item.source_type,
            "title": item.title,
            "score": item.score,
            "metadata": item.metadata,
        }

    def _evidence_text(self, evidence: list[EvidenceDocument]) -> str:
        return "\n".join(
            f"[{index}] {item.title}（{item.source_type}）：{item.content}"
            for index, item in enumerate(evidence, start=1)
        )

    def _memory_text(self, memory: Any) -> str:
        if memory is None:
            return ""
        formatter = getattr(memory, "as_system_prompt", None)
        if callable(formatter):
            return str(formatter())
        if isinstance(memory, dict):
            return json.dumps(memory, ensure_ascii=False, default=str)
        return str(memory)

    def _dedup_route(self, items: list[EvidenceDocument]) -> list[EvidenceDocument]:
        by_source: dict[str, EvidenceDocument] = {}
        for item in items:
            if item.source not in by_source or item.score > by_source[item.source].score:
                by_source[item.source] = item
        return sorted(by_source.values(), key=lambda item: (-item.score, item.source))

    def _estimate_tokens(self, text: str) -> int:
        return max(1, len(str(text or "")) // 4)

    def _provider_name(self, provider: str | None) -> str:
        if provider:
            return provider
        try:
            return str(self.llm.resolve().name)
        except Exception:
            return "unknown"

    def _model_name(self, model: str | None) -> str:
        if model:
            return model
        try:
            return str(self.llm.resolve().model)
        except Exception:
            return "unknown"
