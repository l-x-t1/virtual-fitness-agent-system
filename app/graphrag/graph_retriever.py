"""Graph retriever for fitness GraphRAG."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.graph.cypher_query import CypherQueryService
from app.graph.data_import import load_knowledge_base


@dataclass
class GraphRetrievalResult:
    query: str
    keywords: list[str] = field(default_factory=list)
    knowledge: list[dict[str, Any]] = field(default_factory=list)
    relations: list[dict[str, Any]] = field(default_factory=list)
    context: str = ""


class GraphRetriever:
    """Extract query keywords, retrieve graph knowledge, and build context."""

    def __init__(self, query_service: CypherQueryService | None = None):
        self.query_service = query_service or CypherQueryService()
        self._lexicon: set[str] | None = None

    def retrieve(
        self,
        question: str,
        user_id: int | None = None,
        limit: int = 8,
    ) -> GraphRetrievalResult:
        question = _required_question(question)
        keywords = self.extract_keywords(question)
        search_terms = keywords or [question]

        knowledge: list[dict[str, Any]] = []
        relations: list[dict[str, Any]] = []

        for term in search_terms[:5]:
            search_result = self.query_service.search_training_knowledge(term, limit=limit)
            knowledge.extend(search_result.get("knowledge", []))

        exercise_names = self._select_entity_names(knowledge, "Exercise")
        error_names = self._select_entity_names(knowledge, "ErrorPoint")

        for exercise_name in exercise_names[:3]:
            errors = self.query_service.find_exercise_errors(exercise_name, limit=limit)
            if errors.get("errors"):
                relations.append({"type": "exercise_errors", **errors})

            related = self.query_service.find_related_exercises(exercise_name, limit=limit)
            if related.get("related_exercises"):
                relations.append({"type": "related_exercises", **related})

        for error_name in error_names[:3]:
            plans = self.query_service.find_correction_plan(error_name=error_name, limit=limit)
            if plans.get("plans"):
                relations.append({"type": "correction_plans", **plans})

        if user_id is not None:
            history = self.query_service.find_user_training_history(user_id, limit=min(limit, 10))
            if history.get("records"):
                relations.append({"type": "user_training_history", **history})

        knowledge = _dedupe_dicts(knowledge, ("type", "name"))
        relations = _dedupe_relations(relations)
        context = self.build_context(question, knowledge, relations)

        return GraphRetrievalResult(
            query=question,
            keywords=keywords,
            knowledge=knowledge,
            relations=relations,
            context=context,
        )

    def extract_keywords(self, question: str) -> list[str]:
        """Extract domain keywords using the JSON knowledge-base lexicon."""
        text = question.strip().lower()
        matched = [item for item in self._load_lexicon() if item.lower() in text]

        fallback_terms = ["深蹲", "膝盖", "膝痛", "腰酸", "核心", "减脂", "增肌", "康复"]
        matched.extend(term for term in fallback_terms if term.lower() in text)
        return sorted(set(matched), key=lambda item: (-len(item), item))[:8]

    def build_context(
        self,
        question: str,
        knowledge: list[dict[str, Any]],
        relations: list[dict[str, Any]],
    ) -> str:
        """Convert graph search results into compact LLM context."""
        lines = [f"问题: {question}"]

        if knowledge:
            lines.append("\n[相关实体]")
            for item in knowledge[:10]:
                summary = item.get("summary") or ""
                metadata = item.get("metadata") or {}
                lines.append(f"- {item.get('type')}: {item.get('name')} | {summary} | {metadata}")

        if relations:
            lines.append("\n[关系链路]")
            for relation in relations[:10]:
                relation_type = relation.get("type", "relation")
                if relation_type == "exercise_errors":
                    for error in relation.get("errors", [])[:5]:
                        lines.append(
                            "- Exercise HAS_ERROR ErrorPoint CORRECT_BY Correction: "
                            f"{relation.get('exercise')} -> {error.get('error')} -> "
                            f"{error.get('correction') or error.get('correction_title')}"
                        )
                        if error.get("reason"):
                            lines.append(f"  reason: {error['reason']}")
                elif relation_type == "correction_plans":
                    for plan in relation.get("plans", [])[:5]:
                        lines.append(
                            "- ErrorPoint CORRECT_BY Correction: "
                            f"{plan.get('error')} -> {plan.get('solution') or plan.get('correction_title')}"
                        )
                elif relation_type == "user_training_history":
                    for record in relation.get("records", [])[:5]:
                        lines.append(
                            "- User HAS_RECORD TrainingRecord CONTAINS Exercise: "
                            f"user={record.get('user_id')} exercise={record.get('exercise')} "
                            f"score={record.get('score')} error={record.get('error')}"
                        )
                elif relation_type == "related_exercises":
                    related_names = [item.get("exercise") for item in relation.get("related_exercises", [])[:5]]
                    lines.append(f"- Related exercises for {relation.get('exercise')}: {related_names}")

        if len(lines) == 1:
            lines.append("未从图谱检索到直接相关实体或关系。")

        return "\n".join(lines)

    def _load_lexicon(self) -> set[str]:
        if self._lexicon is not None:
            return self._lexicon

        lexicon: set[str] = set()
        try:
            knowledge_base = load_knowledge_base()
            for exercise in knowledge_base.get("exercises", []):
                lexicon.add(exercise.get("name", ""))
                lexicon.update(exercise.get("muscles", []))
                lexicon.update(exercise.get("body_parts", []))
                lexicon.update(exercise.get("goals", []))
                lexicon.update(exercise.get("equipment", []))
                for error in exercise.get("errors", []):
                    lexicon.add(error.get("name", ""))
                    lexicon.add(error.get("code", ""))
                    correction = error.get("correction") or {}
                    lexicon.add(correction.get("title", ""))
            for plan in knowledge_base.get("training_plans", []):
                lexicon.add(plan.get("goal", ""))
        except Exception:
            lexicon = set()

        self._lexicon = {item for item in lexicon if item}
        return self._lexicon

    @staticmethod
    def _select_entity_names(items: list[dict[str, Any]], entity_type: str) -> list[str]:
        return [
            str(item["name"])
            for item in items
            if item.get("type") == entity_type and item.get("name")
        ]


def _required_question(question: str) -> str:
    question = (question or "").strip()
    if not question:
        raise ValueError("question is required.")
    return question


def _dedupe_dicts(items: list[dict[str, Any]], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    seen = set()
    result = []
    for item in items:
        marker = tuple(item.get(key) for key in keys)
        if marker in seen:
            continue
        seen.add(marker)
        result.append(item)
    return result


def _dedupe_relations(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    result = []
    for item in items:
        marker = (
            item.get("type"),
            item.get("exercise"),
            item.get("error_name"),
            item.get("user_id"),
        )
        if marker in seen:
            continue
        seen.add(marker)
        result.append(item)
    return result
