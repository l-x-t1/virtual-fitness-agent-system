from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from app.ai.knowledge_base import FitnessKnowledgeBase
from app.agents import EvaluateAgent, MotivationAgent, ProfileAgent, RecommendAgent, ReportAgent
from app.agents.embedding_store import ExerciseVectorStore
from app.evaluation.cases import EvaluationCase
from app.evaluation.judge import JudgeResult, LLMAsJudge
from app.llm import LLMClient
from app.ai.rag.pipeline import HybridRAGPipeline


@dataclass(slots=True)
class RegressionResult:
    case_id: str
    entrypoint: str
    question: str
    expected_answer: str
    actual_answer: str
    mode: str
    fallback_reason: str
    latency_ms: float
    citations: list[str] = field(default_factory=list)
    sources: list[dict[str, Any]] = field(default_factory=list)
    retrieval_counts: dict[str, int] = field(default_factory=dict)
    judge: JudgeResult | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "entrypoint": self.entrypoint,
            "question": self.question,
            "expected_answer": self.expected_answer,
            "actual_answer": self.actual_answer,
            "mode": self.mode,
            "fallback_reason": self.fallback_reason,
            "latency_ms": round(self.latency_ms, 3),
            "citations": list(self.citations),
            "sources": list(self.sources),
            "retrieval_counts": dict(self.retrieval_counts),
            "judge": self.judge.to_dict() if self.judge else None,
            "extra": self.extra,
        }


@dataclass(slots=True)
class RegressionReport:
    generated_at: str
    case_count: int
    pass_count: int
    review_count: int
    fail_count: int
    citation_hit_rate: float
    answer_relevance: float
    safety_score: float
    overall_score: float
    degradation_count: int
    average_latency_ms: float
    judge_mode: str
    results: list[RegressionResult] = field(default_factory=list)
    manual_review_cases: list[str] = field(default_factory=list)
    baseline_compare: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "case_count": self.case_count,
            "pass_count": self.pass_count,
            "review_count": self.review_count,
            "fail_count": self.fail_count,
            "citation_hit_rate": round(self.citation_hit_rate, 4),
            "answer_relevance": round(self.answer_relevance, 4),
            "safety_score": round(self.safety_score, 4),
            "overall_score": round(self.overall_score, 4),
            "degradation_count": self.degradation_count,
            "average_latency_ms": round(self.average_latency_ms, 3),
            "judge_mode": self.judge_mode,
            "manual_review_cases": list(self.manual_review_cases),
            "baseline_compare": self.baseline_compare,
            "results": [item.to_dict() for item in self.results],
        }


class _MemoryStub:
    def __init__(self, notes: list[str] | None = None):
        self.notes = [str(item).strip() for item in (notes or []) if str(item).strip()]

    def as_system_prompt(self) -> str:
        if not self.notes:
            return "暂无可用的跨会话记忆。"
        return "【用户记忆】\n" + "\n".join(f"- {item}" for item in self.notes)


class AgentRegressionRunner:
    def __init__(
        self,
        cases: list[EvaluationCase],
        *,
        llm_client: LLMClient | None = None,
        judge: LLMAsJudge | None = None,
    ):
        self.cases = list(cases)
        self.llm_client = llm_client or LLMClient()
        self.judge = judge or LLMAsJudge(self.llm_client)

    def run(self) -> RegressionReport:
        results = [self.run_case(case) for case in self.cases]
        summary = self._summarize(results)
        summary.results = results
        return summary

    def run_case(self, case: EvaluationCase) -> RegressionResult:
        started = time.perf_counter()
        answer, metadata = self._execute_case(case)
        latency_ms = (time.perf_counter() - started) * 1000
        judge = self.judge.judge(
            case,
            actual_answer=answer,
            citations=list(metadata.get("citations") or []),
            sources=list(metadata.get("sources") or []),
            fallback_reason=str(metadata.get("fallback_reason") or ""),
            mode=str(metadata.get("mode") or "unknown"),
            latency_ms=latency_ms,
            metadata=dict(metadata),
        )
        return RegressionResult(
            case_id=case.id,
            entrypoint=case.entrypoint,
            question=case.question,
            expected_answer=case.expected_answer,
            actual_answer=answer,
            mode=str(metadata.get("mode") or "unknown"),
            fallback_reason=str(metadata.get("fallback_reason") or ""),
            latency_ms=latency_ms,
            citations=list(metadata.get("citations") or []),
            sources=list(metadata.get("sources") or []),
            retrieval_counts=dict(metadata.get("retrieval_counts") or {}),
            judge=judge,
            extra=dict(metadata),
        )

    def _execute_case(self, case: EvaluationCase) -> tuple[str, dict[str, Any]]:
        entrypoint = case.entrypoint.lower().strip()
        payload = dict(case.input or {})
        if entrypoint == "chat":
            return self._run_chat_case(case, payload)
        if entrypoint == "profile":
            agent = ProfileAgent(llm_client=self.llm_client)
            result = agent.summarize(
                payload.get("user") or {},
                history=list(payload.get("history") or []),
                behavior=list(payload.get("behavior") or []),
            )
            return json.dumps(result.get("profile") or result, ensure_ascii=False), self._metadata_from_agent(result)
        if entrypoint == "recommend":
            agent = RecommendAgent(llm_client=self.llm_client)
            result = agent.recommend(
                payload.get("user") or {},
                knowledge_base=list(payload.get("knowledge_base") or []),
                history=list(payload.get("history") or []),
                current_exercise=payload.get("current_exercise"),
                top_k=int(payload.get("top_k") or 5),
            )
            return json.dumps(result.get("recommendations") or result, ensure_ascii=False), self._metadata_from_agent(result)
        if entrypoint == "evaluate":
            agent = EvaluateAgent(llm_client=self.llm_client)
            result = agent.evaluate(
                str(payload.get("exercise_name") or case.question or "动作评估"),
                payload.get("raw_score") or 0,
                pose_data=payload.get("pose_data"),
            )
            return json.dumps(result.get("evaluation") or result, ensure_ascii=False), self._metadata_from_agent(result)
        if entrypoint == "motivation":
            agent = MotivationAgent(llm_client=self.llm_client)
            result = agent.settle(
                payload.get("user") or {},
                payload.get("score") or 0,
                payload.get("duration") or 0,
                points=payload.get("points"),
                level=payload.get("level"),
                unlocked_levels=list(payload.get("unlocked_levels") or []),
            )
            return json.dumps(result, ensure_ascii=False), self._metadata_from_agent(result)
        if entrypoint == "report":
            agent = ReportAgent(llm_client=self.llm_client)
            result = agent.build_report(
                list(payload.get("training_records") or []),
                report_type=str(payload.get("report_type") or "weekly"),
                profile=payload.get("profile"),
            )
            return json.dumps(result, ensure_ascii=False), self._metadata_from_agent(result)
        raise ValueError(f"Unsupported evaluation entrypoint: {case.entrypoint}")

    def _run_chat_case(self, case: EvaluationCase, payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        knowledge = FitnessKnowledgeBase()
        pipeline = HybridRAGPipeline(knowledge_base=knowledge, llm=self.llm_client)
        memory = _MemoryStub(list(payload.get("memory_notes") or []))
        question = payload.get("question") or case.question
        result = pipeline.run(
            str(question),
            recent_messages=list(payload.get("recent_messages") or []),
            memory=memory,
            user_id=int(payload.get("user_id") or 1),
            provider=payload.get("provider"),
            model=payload.get("model"),
            top_k=int(payload.get("top_k") or 5),
        )
        metadata = {
            "mode": result.mode,
            "fallback_reason": result.fallback_reason,
            "citations": list(result.citations),
            "sources": list(result.sources),
            "retrieval_counts": dict(result.retrieval_counts),
            "rewrite_mode": result.rewrite_mode,
            "rerank_mode": result.rerank_mode,
        }
        return result.answer, metadata

    def _metadata_from_agent(self, result: dict[str, Any]) -> dict[str, Any]:
        metadata = dict(result)
        metadata.setdefault("citations", [])
        metadata.setdefault("sources", [])
        metadata.setdefault("retrieval_counts", {})
        return metadata

    def _summarize(self, results: list[RegressionResult]) -> RegressionReport:
        case_count = len(results)
        pass_count = sum(1 for item in results if item.judge and item.judge.verdict == "pass")
        review_count = sum(1 for item in results if item.judge and item.judge.verdict == "review")
        fail_count = sum(1 for item in results if item.judge and item.judge.verdict == "fail")
        citation_cases = [item for item in results if item.judge and item.citations]
        citation_hit_rate = (
            sum(item.judge.citation_hit_rate for item in citation_cases if item.judge) / len(citation_cases)
            if citation_cases
            else 0.0
        )
        answer_relevance = self._average(item.judge.relevance for item in results if item.judge)
        safety_score = self._average(item.judge.safety for item in results if item.judge)
        overall_score = self._average(item.judge.overall for item in results if item.judge)
        degradation_count = sum(
            1
            for item in results
            if item.mode.lower() in {"fallback", "demo"} or (item.judge and item.judge.verdict != "pass")
        )
        average_latency_ms = self._average(item.latency_ms for item in results)
        manual_review_cases = [item.case_id for item in results if item.judge and item.judge.manual_review]
        judge_mode = "llm-as-judge" if any(item.judge and item.judge.judge_mode == "llm-as-judge" for item in results) else "heuristic"
        return RegressionReport(
            generated_at=datetime.utcnow().isoformat() + "Z",
            case_count=case_count,
            pass_count=pass_count,
            review_count=review_count,
            fail_count=fail_count,
            citation_hit_rate=citation_hit_rate,
            answer_relevance=answer_relevance,
            safety_score=safety_score,
            overall_score=overall_score,
            degradation_count=degradation_count,
            average_latency_ms=average_latency_ms,
            judge_mode=judge_mode,
            manual_review_cases=manual_review_cases,
        )

    def _average(self, values) -> float:
        items = [float(value) for value in values]
        return round(sum(items) / len(items), 4) if items else 0.0
