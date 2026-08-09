from __future__ import annotations

import json
import re
from typing import Any

from app.ai.llm import AIProviderError
from app.ai.rag.schemas import RewriteResult
from app.agents.output_parser import OutputParser


class QueryRewriter:
    """Conversation-aware query rewrite with a deterministic local path."""

    def __init__(self, llm: Any | None = None, max_queries: int = 3):
        self.llm = llm
        self.max_queries = max(1, min(int(max_queries), 5))
        self.parser = OutputParser()

    def rewrite(
        self,
        question: str,
        recent_messages: list[dict[str, Any]] | None = None,
        memory: Any | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> RewriteResult:
        original = self._clean(question)
        if self.llm is not None:
            try:
                prompt = self._prompt(original, recent_messages or [], memory)
                raw = self.llm.chat(
                    [
                        {"role": "system", "content": "你是健身知识库检索查询改写器，只返回 JSON。"},
                        {"role": "user", "content": prompt},
                    ],
                    provider,
                    model,
                    temperature=0,
                )
                payload = self.parser.loads(raw)
                queries = self._validate_queries(payload.get("queries"), original)
                if queries:
                    return RewriteResult(
                        original_query=original,
                        queries=queries,
                        mode="online",
                    )
            except (AIProviderError, ValueError, TypeError, AttributeError):
                pass
        return RewriteResult(
            original_query=original,
            queries=self._fallback_queries(original, recent_messages or [], memory),
            mode="fallback",
            fallback_reason="llm_unavailable_or_invalid",
        )

    def _prompt(self, question: str, recent_messages: list[dict[str, Any]], memory: Any) -> str:
        recent = [
            {"role": item.get("role"), "content": str(item.get("content") or "")[:300]}
            for item in recent_messages[-6:]
        ]
        return (
            "根据原始问题、最近对话和用户记忆生成 1 到 3 个简短检索查询。"
            "保留动作、目标、伤病限制等关键实体，不回答问题，不补充不存在的疾病。"
            '输出：{"queries":["查询1","查询2"]}\n'
            f"原始问题：{question}\n"
            f"最近对话：{json.dumps(recent, ensure_ascii=False)}\n"
            f"用户记忆：{self._memory_text(memory)[:1200]}"
        )

    def _fallback_queries(self, question: str, recent_messages: list[dict[str, Any]], memory: Any) -> list[str]:
        context = " ".join(
            str(item.get("content") or "")
            for item in recent_messages[-4:]
            if item.get("role") == "user"
        )
        memory_text = self._memory_text(memory)
        combined = f"{question} {context} {memory_text}"
        keywords = self._keywords(combined)
        queries = [question]
        if keywords:
            expanded = " ".join(keywords[:10])
            if expanded and expanded != question:
                queries.append(expanded)
        safety = [
            word
            for word in ("膝盖", "膝", "腰", "踝", "疼痛", "受伤", "低冲击")
            if word in combined
        ]
        if safety:
            queries.append(f"{question} {' '.join(safety)} 安全 低冲击")
        return list(dict.fromkeys(self._clean(item) for item in queries if self._clean(item)))[: self.max_queries]

    def _validate_queries(self, raw: Any, original: str) -> list[str]:
        if not isinstance(raw, list):
            return []
        queries = [original]
        for item in raw:
            value = self._clean(item)
            if value and value not in queries:
                queries.append(value)
        return queries[: self.max_queries]

    def _memory_text(self, memory: Any) -> str:
        if memory is None:
            return ""
        formatter = getattr(memory, "as_system_prompt", None)
        if callable(formatter):
            value = str(formatter())
            return "" if value.startswith("暂无可用的跨会话记忆") else value
        if isinstance(memory, dict):
            return json.dumps(memory, ensure_ascii=False, default=str)
        return str(memory)

    def _keywords(self, text: str) -> list[str]:
        terms = re.findall(r"[\u4e00-\u9fff]{1,8}|[a-z0-9]+", text.lower())
        stop = {"我", "的", "了", "呢", "吗", "请", "帮我", "怎么", "什么", "一下", "用户", "记忆"}
        return list(dict.fromkeys(term for term in terms if term not in stop))

    def _clean(self, value: Any) -> str:
        return re.sub(r"\s+", " ", str(value or "")).strip()[:500]
