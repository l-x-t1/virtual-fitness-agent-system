"""GraphRAG chain for fitness QA."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.graphrag.graph_prompt import build_graph_rag_prompt
from app.graphrag.graph_retriever import GraphRetrievalResult, GraphRetriever
from app.llm.client import LLMClient, LLMConfigurationError


@dataclass
class GraphRAGAnswer:
    query: str
    answer: str
    knowledge: list[dict[str, Any]]
    relations: list[dict[str, Any]]
    context: str
    keywords: list[str]
    used_llm: bool = False

    def model_dump(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "answer": self.answer,
            "knowledge": self.knowledge,
            "relations": self.relations,
            "context": self.context,
            "keywords": self.keywords,
            "used_llm": self.used_llm,
        }


class GraphRAGChain:
    """Retrieve graph context and generate a coach-style answer."""

    def __init__(
        self,
        retriever: GraphRetriever | None = None,
        llm_client: LLMClient | None = None,
        use_llm: bool = True,
    ):
        self.retriever = retriever or GraphRetriever()
        self.llm_client = llm_client
        self.use_llm = use_llm

    def invoke(self, question: str, user_id: int | None = None, limit: int = 8) -> dict[str, Any]:
        return self.run(question=question, user_id=user_id, limit=limit).model_dump()

    def run(self, question: str, user_id: int | None = None, limit: int = 8) -> GraphRAGAnswer:
        retrieval = self.retriever.retrieve(question, user_id=user_id, limit=limit)
        answer, used_llm = self._generate_answer(retrieval)
        return GraphRAGAnswer(
            query=question,
            answer=answer,
            knowledge=retrieval.knowledge,
            relations=retrieval.relations,
            context=retrieval.context,
            keywords=retrieval.keywords,
            used_llm=used_llm,
        )

    def _generate_answer(self, retrieval: GraphRetrievalResult) -> tuple[str, bool]:
        if self.use_llm:
            try:
                llm = self.llm_client or LLMClient()
                prompt = build_graph_rag_prompt(retrieval.query, retrieval.context)
                return llm.invoke(prompt), True
            except (LLMConfigurationError, ValueError, RuntimeError) as exc:
                return self._fallback_answer(retrieval, note=str(exc)), False
            except Exception as exc:
                return self._fallback_answer(retrieval, note=f"LLM generation failed: {exc}"), False

        return self._fallback_answer(retrieval), False

    def _fallback_answer(self, retrieval: GraphRetrievalResult, note: str | None = None) -> str:
        errors = _collect_error_items(retrieval.relations)
        plans = _collect_plan_items(retrieval.relations)

        lines = []
        if errors:
            first = errors[0]
            lines.append(f"可能原因：{first.get('reason') or first.get('description') or '图谱中存在相关动作错误点。'}")
            lines.append(f"关联错误：{first.get('exercise', '')} - {first.get('error', '')}".strip())
            correction = first.get("correction") or first.get("correction_title")
            if correction:
                lines.append(f"纠正建议：{correction}")
            if first.get("drills"):
                lines.append(f"辅助训练：{first['drills']}")
            if first.get("safety_note"):
                lines.append(f"安全提醒：{first['safety_note']}")
        elif plans:
            first = plans[0]
            lines.append(f"纠正建议：{first.get('solution') or first.get('correction_title') or '按图谱纠正方案降低强度并重建动作控制。'}")
            if first.get("drills"):
                lines.append(f"辅助训练：{first['drills']}")
            if first.get("safety_note"):
                lines.append(f"安全提醒：{first['safety_note']}")
        elif retrieval.knowledge:
            first = retrieval.knowledge[0]
            lines.append(f"相关知识：{first.get('name')} - {first.get('summary', '')}")
            lines.append("建议：先按标准动作降低强度练习，再根据疼痛或错误表现选择纠正训练。")
        else:
            lines.append("暂未从知识图谱检索到直接匹配内容。建议补充动作名称、疼痛部位或具体错误表现。")

        if "疼" in retrieval.query or "痛" in retrieval.query or "不适" in retrieval.query:
            lines.append("安全提醒：如果疼痛持续、加重，或伴随肿胀、麻木，请停止训练并寻求专业评估。")

        if note:
            lines.append(f"生成说明：当前使用图谱降级回答，LLM 未启用或不可用。")

        return "\n".join(line for line in lines if line)


def _collect_error_items(relations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for relation in relations:
        if relation.get("type") != "exercise_errors":
            continue
        exercise = relation.get("exercise")
        for item in relation.get("errors", []):
            result.append({"exercise": exercise, **item})
    return result


def _collect_plan_items(relations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for relation in relations:
        if relation.get("type") != "correction_plans":
            continue
        result.extend(relation.get("plans", []))
    return result
