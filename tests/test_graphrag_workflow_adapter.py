"""人员 3：GraphRAG LangGraph 薄适配节点测试。"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import app.ai.langgraph_agent as workflow


def _state(question: str) -> dict:
    return {
        "messages": [{"role": "user", "content": question}],
        "user_info": {"id": "12"},
        "task_plan": {"goal": "康复"},
        "recommendations": [],
        "evaluation": {},
        "motivation": "",
        "report": {},
        "graph_context": {},
        "route": "graphrag",
        "retry_count": 0,
        "max_retries": 1,
        "error": {},
        "completed_steps": [],
    }


class FakeAvailableGraphService:
    def status(self):
        return SimpleNamespace(available=True)

    def search(self, query, user_id=None, top_k=8, use_llm=False):
        assert query == "深蹲膝盖疼怎么办"
        assert user_id == 12
        assert top_k == 8
        assert use_llm is False
        return SimpleNamespace(model_dump=lambda: {
            "query": query,
            "knowledge": [{"title": "深蹲动作要点"}],
            "relations": [{"source": "深蹲", "target": "膝关节"}],
            "answer": "先降低负荷并检查膝盖与脚尖方向。",
        })


class FakeUnavailableGraphService:
    def status(self):
        return SimpleNamespace(available=False)


def test_graphrag_result_is_written_to_state(monkeypatch):
    monkeypatch.setattr(workflow, "_make_graph_service", FakeAvailableGraphService)
    update = workflow.graphrag_node(_state("深蹲膝盖疼怎么办"))
    assert update["graph_context"]["status"] == "available"
    assert update["graph_context"]["knowledge"]
    assert update["graph_context"]["relations"]
    assert update["route"] == "report"


def test_neo4j_unavailable_is_a_safe_degradation(monkeypatch):
    monkeypatch.setattr(workflow, "_make_graph_service", FakeUnavailableGraphService)
    update = workflow.graphrag_node(_state("深蹲膝盖疼怎么办"))
    assert update["graph_context"]["status"] == "unavailable"
    assert update["graph_context"]["knowledge"] == []
    assert update["fallback_reason"] == "neo4j_unavailable"
    assert update["route"] == "report"


def test_graphrag_degradation_still_reaches_end(monkeypatch):
    monkeypatch.setattr(workflow, "_make_graph_service", FakeUnavailableGraphService)
    monkeypatch.setattr(workflow, "_plan_via_llm", lambda *_: None)
    monkeypatch.setattr(workflow, "_report_via_llm", lambda *_: None)
    result = asyncio.run(workflow.compiled_graph.ainvoke(_state("深蹲膝盖疼怎么办")))
    assert result["current_step"] == "done"
    assert result["graph_context"]["status"] == "unavailable"
    assert result["report"]["summary"]


def test_graph_service_exception_does_not_escape(monkeypatch):
    def explode():
        raise ConnectionError("neo4j offline")

    monkeypatch.setattr(workflow, "_make_graph_service", explode)
    update = workflow.graphrag_node(_state("深蹲膝盖疼怎么办"))
    assert update["graph_context"]["status"] == "unavailable"
    assert update["graph_context"]["reason"] == "graphrag_failed"
    assert "neo4j offline" not in str(update)
