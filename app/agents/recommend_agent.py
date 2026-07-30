from __future__ import annotations

from typing import Any

from app.agents.base import BaseAgent
from app.agents.embedding_store import ExerciseVectorStore
from app.agents.schemas import RecommendOutput, RecommendationItem


class RecommendAgent(BaseAgent):
    prompt_module = "app.agents.prompts.recommend_prompt"
    output_schema = RecommendOutput

    def __init__(
        self,
        *args: Any,
        vector_store: ExerciseVectorStore | None = None,
        knowledge_base: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ):
        super().__init__(*args, **kwargs)
        self.vector_store = vector_store or ExerciseVectorStore()
        self.knowledge_base = list(knowledge_base or [])

    def recommend(
        self,
        user: dict[str, Any],
        knowledge_base: list[dict[str, Any]] | None = None,
        history: list[dict[str, Any]] | None = None,
        current_exercise: str | None = None,
        top_k: int = 5,
    ) -> dict[str, Any]:
        candidates = self._retrieve(user, knowledge_base, history, current_exercise, top_k)
        if not candidates:
            return {
                "recommendations": [],
                "retrieval_backend": self.vector_store.last_backend,
                **self.fallback_metadata(reason="empty_knowledge_base"),
            }
        payload = self._payload(user, history, current_exercise, candidates)
        try:
            result = self.run(payload)
            recommendations = self._whitelist(result["recommendations"], candidates)
            if not recommendations:
                return self._fallback_result(
                    user, candidates, "model_returned_no_valid_candidates"
                )
            return {
                "recommendations": recommendations,
                "retrieval_backend": self.vector_store.last_backend,
                **self.online_metadata(),
            }
        except self.recoverable_errors as exc:
            return self._fallback_result(user, candidates, self._safe_reason(exc))

    async def arecommend(
        self,
        user: dict[str, Any],
        knowledge_base: list[dict[str, Any]] | None = None,
        history: list[dict[str, Any]] | None = None,
        current_exercise: str | None = None,
        top_k: int = 5,
    ) -> dict[str, Any]:
        candidates = self._retrieve(user, knowledge_base, history, current_exercise, top_k)
        if not candidates:
            return {
                "recommendations": [],
                "retrieval_backend": self.vector_store.last_backend,
                **self.fallback_metadata(reason="empty_knowledge_base"),
            }
        payload = self._payload(user, history, current_exercise, candidates)
        try:
            result = await self.arun(payload)
            recommendations = self._whitelist(result["recommendations"], candidates)
            if not recommendations:
                return self._fallback_result(
                    user, candidates, "model_returned_no_valid_candidates"
                )
            return {
                "recommendations": recommendations,
                "retrieval_backend": self.vector_store.last_backend,
                **self.online_metadata(),
            }
        except self.recoverable_errors as exc:
            return self._fallback_result(user, candidates, self._safe_reason(exc))

    def _retrieve(
        self,
        user: dict[str, Any],
        knowledge_base: list[dict[str, Any]] | None,
        history: list[dict[str, Any]] | None,
        current_exercise: str | None,
        top_k: int,
    ) -> list[dict[str, Any]]:
        exercises = list(self.knowledge_base if knowledge_base is None else knowledge_base)
        return self.vector_store.search(
            user,
            exercises,
            exercise_name=current_exercise,
            top_k=min(max(1, top_k), 5),
            history=history or [],
        )

    def _payload(
        self,
        user: dict[str, Any],
        history: list[dict[str, Any]] | None,
        current_exercise: str | None,
        candidates: list[dict[str, Any]],
    ) -> dict[str, Any]:
        fields = ("name", "category", "difficulty", "target", "equipment", "retrieval_score")
        return {
            "profile": dict(user or {}),
            "history": list(history or []),
            "current_exercise": current_exercise,
            "retrieval_context": [item.get("rag_context", "") for item in candidates],
            "candidates": [{field: item.get(field) for field in fields} for item in candidates],
        }

    def _whitelist(
        self,
        recommendations: list[dict[str, Any]],
        candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        allowed = {item["name"] for item in candidates}
        output = []
        used = set()
        for item in recommendations:
            name = item.get("name")
            if name not in allowed or name in used:
                continue
            output.append(RecommendationItem.model_validate(item).model_dump())
            used.add(name)
        return output[:5]

    def _fallback_result(
        self,
        user: dict[str, Any],
        candidates: list[dict[str, Any]],
        reason: str,
    ) -> dict[str, Any]:
        injuries = user.get("injuries") or user.get("risk_flags")
        recommendations = []
        for item in candidates[:5]:
            score = float(item.get("retrieval_score") or item.get("rag_score") or 0)
            target = item.get("target") or item.get("category") or "训练目标"
            warning = str(item.get("risk_warning") or "")
            if injuries and not warning:
                warning = "存在已输入的伤病/不适信息，请按个人耐受控制动作。"
            recommendations.append(
                RecommendationItem(
                    name=item["name"],
                    score=max(0, min(100, score)),
                    reason=f"本地语义检索显示该动作与用户信息及{target}相关。",
                    risk_warning=warning,
                ).model_dump()
            )
        return {
            "recommendations": recommendations,
            "retrieval_backend": self.vector_store.last_backend,
            **self.fallback_metadata(reason=reason),
        }
