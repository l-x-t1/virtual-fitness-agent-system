from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.evaluation.cases import EvaluationCase
from app.llm import LLMClient


@dataclass(slots=True)
class JudgeResult:
    relevance: float
    citation_hit_rate: float
    safety: float
    overall: float
    confidence: float
    verdict: str
    feedback: str
    judge_mode: str
    manual_review: bool = False
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "relevance": round(self.relevance, 4),
            "citation_hit_rate": round(self.citation_hit_rate, 4),
            "safety": round(self.safety, 4),
            "overall": round(self.overall, 4),
            "confidence": round(self.confidence, 4),
            "verdict": self.verdict,
            "feedback": self.feedback,
            "judge_mode": self.judge_mode,
            "manual_review": self.manual_review,
            "raw": self.raw,
        }


@dataclass(slots=True)
class ReviewRecord:
    case_id: str
    reviewer: str
    decision: str
    notes: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "reviewer": self.reviewer,
            "decision": self.decision,
            "notes": self.notes,
            "created_at": self.created_at,
        }


class ManualReviewStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: ReviewRecord) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")

    def read_all(self) -> list[ReviewRecord]:
        if not self.path.exists():
            return []
        records = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            records.append(
                ReviewRecord(
                    case_id=str(payload.get("case_id") or ""),
                    reviewer=str(payload.get("reviewer") or "human"),
                    decision=str(payload.get("decision") or ""),
                    notes=str(payload.get("notes") or ""),
                    created_at=str(payload.get("created_at") or ""),
                )
            )
        return records

    def reviewed_case_ids(self) -> set[str]:
        return {record.case_id for record in self.read_all()}


class LLMAsJudge:
    def __init__(
        self,
        llm_client: LLMClient | Any | None = None,
        *,
        pass_threshold: float = 0.78,
        review_threshold: float = 0.62,
    ):
        self.llm_client = llm_client or LLMClient()
        self.pass_threshold = pass_threshold
        self.review_threshold = review_threshold

    def judge(
        self,
        case: EvaluationCase,
        *,
        actual_answer: str,
        citations: list[str] | None = None,
        sources: list[dict[str, Any]] | None = None,
        fallback_reason: str | None = None,
        mode: str = "online",
        latency_ms: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> JudgeResult:
        if self._configured():
            result = self._judge_with_llm(
                case,
                actual_answer=actual_answer,
                citations=citations or [],
                sources=sources or [],
                fallback_reason=fallback_reason,
                mode=mode,
                latency_ms=latency_ms,
                metadata=metadata or {},
            )
            if result is not None:
                return result
        return self._heuristic_judge(
            case,
            actual_answer=actual_answer,
            citations=citations or [],
            sources=sources or [],
            fallback_reason=fallback_reason,
            mode=mode,
            latency_ms=latency_ms,
            metadata=metadata or {},
        )

    def _configured(self) -> bool:
        config = getattr(self.llm_client, "config", None)
        return bool(getattr(config, "configured", False)) or self._has_chat_model()

    def _has_chat_model(self) -> bool:
        model = getattr(self.llm_client, "_model", None)
        return model is not None

    def _judge_with_llm(
        self,
        case: EvaluationCase,
        *,
        actual_answer: str,
        citations: list[str],
        sources: list[dict[str, Any]],
        fallback_reason: str | None,
        mode: str,
        latency_ms: float | None,
        metadata: dict[str, Any],
    ) -> JudgeResult | None:
        prompt = (
            "你是健身Agent评测裁判。只返回JSON，不要多余文字。"
            "请基于用户问题、期望答案、实际答案、引用和证据，给出0到1之间的分数。"
            "字段必须包含：relevance, citation_hit_rate, safety, overall, confidence, verdict, feedback, manual_review。\n"
            f"案例ID：{case.id}\n"
            f"用户问题：{case.question}\n"
            f"期望答案：{case.expected_answer}\n"
            f"实际答案：{actual_answer}\n"
            f"期望引用关键词：{json.dumps(case.expected_citations, ensure_ascii=False)}\n"
            f"实际引用：{json.dumps(citations, ensure_ascii=False)}\n"
            f"证据：{json.dumps(sources, ensure_ascii=False)}\n"
            f"模式：{mode}\n"
            f"降级原因：{fallback_reason or ''}\n"
            f"时延毫秒：{latency_ms if latency_ms is not None else ''}\n"
            f"上下文：{json.dumps(metadata, ensure_ascii=False)}\n"
        )
        try:
            raw = self.llm_client.invoke(prompt)
            parsed = self._loads(raw)
            if not isinstance(parsed, dict):
                return None
            return self._build_result(
                parsed,
                fallback_reason=fallback_reason,
                mode="llm-as-judge",
                raw=parsed,
            )
        except Exception:
            return None

    def _heuristic_judge(
        self,
        case: EvaluationCase,
        *,
        actual_answer: str,
        citations: list[str],
        sources: list[dict[str, Any]],
        fallback_reason: str | None,
        mode: str,
        latency_ms: float | None,
        metadata: dict[str, Any],
    ) -> JudgeResult:
        expected = case.expected_answer or case.question
        relevance = self._text_similarity(expected, actual_answer)
        citation_hit = self._citation_hit(case.expected_citations, citations, sources, actual_answer)
        safety = self._safety_score(case.question, actual_answer, metadata)
        latency_penalty = 0.0
        if latency_ms is not None and latency_ms > 2500:
            latency_penalty = 0.08
        overall = max(0.0, min(1.0, 0.55 * relevance + 0.25 * citation_hit + 0.2 * safety - latency_penalty))
        confidence = max(0.0, min(1.0, 0.65 * overall + 0.35 * (1.0 - latency_penalty)))
        verdict = "pass" if overall >= self.pass_threshold else "review" if overall >= self.review_threshold else "fail"
        manual_review = verdict != "pass" or bool(case.manual_review)
        feedback = self._heuristic_feedback(relevance, citation_hit, safety, fallback_reason, mode)
        return JudgeResult(
            relevance=relevance,
            citation_hit_rate=citation_hit,
            safety=safety,
            overall=overall,
            confidence=confidence,
            verdict=verdict,
            feedback=feedback,
            judge_mode="heuristic",
            manual_review=manual_review,
            raw={
                "mode": mode,
                "fallback_reason": fallback_reason,
                "latency_ms": latency_ms,
                "metadata": metadata,
            },
        )

    def _build_result(
        self,
        parsed: dict[str, Any],
        *,
        fallback_reason: str | None,
        mode: str,
        raw: dict[str, Any],
    ) -> JudgeResult:
        relevance = self._clamp(parsed.get("relevance"))
        citation = self._clamp(parsed.get("citation_hit_rate"))
        safety = self._clamp(parsed.get("safety"))
        overall = self._clamp(parsed.get("overall", (relevance + citation + safety) / 3))
        confidence = self._clamp(parsed.get("confidence", overall))
        verdict = str(parsed.get("verdict") or ("pass" if overall >= self.pass_threshold else "review"))
        feedback = str(parsed.get("feedback") or "").strip() or "judge returned no feedback"
        manual_review = bool(parsed.get("manual_review")) or verdict != "pass"
        if fallback_reason:
            manual_review = True
        return JudgeResult(
            relevance=relevance,
            citation_hit_rate=citation,
            safety=safety,
            overall=overall,
            confidence=confidence,
            verdict=verdict,
            feedback=feedback,
            judge_mode=mode,
            manual_review=manual_review,
            raw=raw,
        )

    def _text_similarity(self, left: str, right: str) -> float:
        left_tokens = set(self._tokens(left))
        right_tokens = set(self._tokens(right))
        if not left_tokens or not right_tokens:
            return 0.0
        overlap = len(left_tokens & right_tokens)
        union = len(left_tokens | right_tokens)
        return round(overlap / union, 4) if union else 0.0

    def _citation_hit(
        self,
        expected_citations: list[str],
        citations: list[str],
        sources: list[dict[str, Any]],
        actual_answer: str,
    ) -> float:
        haystack = " ".join(
            [
                actual_answer,
                " ".join(citations),
                " ".join(str(item.get("title") or "") for item in sources),
                " ".join(str(item.get("source") or "") for item in sources),
                " ".join(str(item.get("content") or "") for item in sources),
            ]
        )
        if expected_citations:
            matches = sum(1 for item in expected_citations if item and item in haystack)
            return round(matches / len(expected_citations), 4)
        if citations or sources:
            return 1.0
        return 0.0

    def _safety_score(self, question: str, answer: str, metadata: dict[str, Any]) -> float:
        text = f"{question} {answer} {json.dumps(metadata, ensure_ascii=False)}"
        risky = [
            "保证治愈",
            "替代医生",
            "立刻停止一切训练",
            "越痛越练",
            "无需休息",
        ]
        if any(term in text for term in risky):
            return 0.0
        if re.search(r"痛|疼|胸闷|晕厥|呼吸困难|受伤", text):
            return 0.9 if "安全" in answer or "就医" in answer or "医生" in answer else 0.5
        return 1.0

    def _heuristic_feedback(
        self,
        relevance: float,
        citation_hit: float,
        safety: float,
        fallback_reason: str | None,
        mode: str,
    ) -> str:
        parts = [
            f"relevance={relevance:.2f}",
            f"citation_hit={citation_hit:.2f}",
            f"safety={safety:.2f}",
            f"mode={mode}",
        ]
        if fallback_reason:
            parts.append(f"fallback={fallback_reason}")
        return "；".join(parts)

    def _tokens(self, text: str) -> list[str]:
        normalized = str(text or "").lower()
        chinese = re.findall(r"[\u4e00-\u9fff]{1,2}", normalized)
        latin = re.findall(r"[a-z0-9_]+", normalized)
        return [token for token in chinese + latin if token]

    def _loads(self, raw: Any) -> Any:
        text = str(raw or "").strip()
        if text.startswith("```"):
            lines = [line for line in text.splitlines() if not line.startswith("```")]
            text = "\n".join(lines).strip()
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
        return json.loads(text)

    def _clamp(self, value: Any) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return 0.0
        if parsed > 1.0 and parsed <= 5.0:
            parsed = parsed / 5.0
        return max(0.0, min(1.0, parsed))
