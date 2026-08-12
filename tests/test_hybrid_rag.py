from __future__ import annotations

import json
from types import SimpleNamespace

from app.ai.knowledge_base import FitnessKnowledgeBase
from app.ai.memory import MemoryContext
from app.ai.rag.bm25_retriever import BM25Retriever
from app.ai.rag.fusion import ResultFusion
from app.ai.rag.graph_retriever import GraphRetriever
from app.ai.rag.pipeline import HybridRAGPipeline
from app.ai.rag.query_rewriter import QueryRewriter
from app.ai.rag.reranker import EvidenceReranker
from app.ai.rag.schemas import EvidenceDocument
from app.ai.rag.vector_retriever import VectorRetriever
from app.llm import LLMClient, LLMError


class OfflineLLM(LLMClient):
    def chat(self, *args, **kwargs):
        raise LLMError("offline")


class RoutingLLM(LLMClient):
    def __init__(self):
        self.prompts = []

    def chat(self, messages, *args, **kwargs):
        prompt = messages[-1]["content"]
        self.prompts.append(prompt)
        if "生成 1 到 3 个简短检索查询" in prompt:
            return json.dumps({"queries": ["深蹲 膝盖 安全", "膝部低冲击替代"]}, ensure_ascii=False)
        if "候选证据" in prompt:
            candidates = json.loads(prompt.split("候选：", 1)[1])
            return json.dumps(
                {"ranking": [{"source": candidates[0]["source"], "score": 0.98}]},
                ensure_ascii=False,
            )
        return "根据证据，深蹲应保持膝盖与脚尖方向一致。[1]"

    def resolve(self, provider=None, model=None):
        return SimpleNamespace(name=provider or "deepseek", model=model or "fake-model")


def docs():
    return [
        {"id": "squat", "title": "深蹲动作要点", "category": "动作", "content": "深蹲时膝盖与脚尖方向保持一致。"},
        {"id": "plank", "title": "平板支撑", "category": "动作", "content": "平板支撑时收紧核心并保持自然呼吸。"},
        {"id": "knee", "title": "膝部低冲击替代", "category": "安全", "content": "膝部不适时可选择臀桥或低冲击骑行。"},
    ]


def test_query_rewrite_online_and_fallback():
    online = QueryRewriter(RoutingLLM()).rewrite("深蹲膝盖怎么保护", [], None)
    assert online.mode == "online"
    assert online.queries[0] == "深蹲膝盖怎么保护"
    fallback = QueryRewriter(OfflineLLM()).rewrite(
        "给我训练建议",
        [{"role": "user", "content": "我想练深蹲"}],
        MemoryContext([], [{"category": "body_issue", "content": "膝盖不适"}], []),
    )
    assert fallback.mode == "fallback"
    assert any("膝" in query for query in fallback.queries)


def test_bm25_chinese_keyword_recall():
    retriever = BM25Retriever(docs())
    results = retriever.retrieve("深蹲时膝盖方向", top_k=2)
    assert results
    assert results[0].source == "knowledge:squat"
    assert results[0].metadata["retrieval_backend"] in {"rank-bm25", "local-keyword"}


def test_vector_recall_and_chroma_local_fallback(tmp_path):
    source = tmp_path / "knowledge.json"
    source.write_text(json.dumps(docs(), ensure_ascii=False), encoding="utf-8")
    knowledge = FitnessKnowledgeBase(source=source, custom_source=tmp_path / "custom.json")
    normal = VectorRetriever(knowledge).retrieve("核心 平板支撑", top_k=2)
    assert any(item.source == "knowledge:plank" for item in normal)
    knowledge._ensure_vector_index = lambda: False
    fallback = VectorRetriever(knowledge).retrieve("核心 平板支撑", top_k=2)
    assert fallback
    assert all(item.metadata["retrieval_backend"] == "local-semantic" for item in fallback)


def test_graph_unavailable_returns_empty_without_raising():
    service = SimpleNamespace(status=lambda: SimpleNamespace(available=False))
    retriever = GraphRetriever(service_factory=lambda: service)
    assert retriever.retrieve("推荐动作", user_id=1) == []
    assert retriever.last_error == "neo4j_unavailable"


def test_three_way_fusion_deduplicates_and_normalizes():
    duplicate_a = EvidenceDocument(source="knowledge:squat", source_type="bm25", title="深蹲", content="动作说明", score=0.8)
    duplicate_b = EvidenceDocument(source="knowledge:squat", source_type="vector", title="深蹲", content="更完整的动作说明", score=0.9)
    graph = EvidenceDocument(source="graph:relation-1", source_type="graph", title="深蹲关系", content="深蹲涉及下肢", score=0.7)
    fused = ResultFusion().fuse({"bm25": [duplicate_a], "vector": [duplicate_b], "graph": [graph]})
    assert len(fused) == 2
    squat = next(item for item in fused if item.source == "knowledge:squat")
    assert squat.source_type == "hybrid"
    assert squat.metadata["matched_source_types"] == ["bm25", "vector"]
    assert all(0 <= item.score <= 1 for item in fused)


def test_rerank_online_and_fallback():
    items = [
        EvidenceDocument(source="knowledge:squat", source_type="hybrid", title="深蹲", content="膝盖脚尖一致", score=0.8),
        EvidenceDocument(source="knowledge:plank", source_type="vector", title="平板", content="核心稳定", score=0.6),
    ]
    online = EvidenceReranker(RoutingLLM()).rerank("深蹲膝盖", items)
    assert online.mode == "online"
    assert online.documents[0].source == "knowledge:squat"
    fallback = EvidenceReranker(OfflineLLM()).rerank("深蹲膝盖", items)
    assert fallback.mode == "fallback"
    assert fallback.documents[0].metadata["rerank_mode"] == "local"


def test_complete_rag_demo_returns_sources_without_api_key(tmp_path):
    source = tmp_path / "knowledge.json"
    source.write_text(json.dumps(docs(), ensure_ascii=False), encoding="utf-8")
    knowledge = FitnessKnowledgeBase(source=source, custom_source=tmp_path / "custom.json")
    graph = GraphRetriever(service_factory=lambda: SimpleNamespace(status=lambda: SimpleNamespace(available=False)))
    pipeline = HybridRAGPipeline(knowledge, OfflineLLM(), graph_retriever=graph)
    result = pipeline.run("深蹲时膝盖疼怎么办", user_id=1)
    assert result.mode == "fallback"
    assert result.sources and result.citations
    assert "不能替代医生诊断" in result.answer
    assert result.retrieval_counts["graph"] == 0


def test_memory_is_used_by_rewrite_rerank_and_answer(tmp_path):
    source = tmp_path / "knowledge.json"
    source.write_text(json.dumps(docs(), ensure_ascii=False), encoding="utf-8")
    llm = RoutingLLM()
    pipeline = HybridRAGPipeline(
        FitnessKnowledgeBase(source=source, custom_source=tmp_path / "custom.json"),
        llm,
        graph_retriever=GraphRetriever(service_factory=lambda: SimpleNamespace(status=lambda: SimpleNamespace(available=False))),
    )
    memory = MemoryContext([], [{"category": "body_issue", "content": "膝盖不适"}], [])
    result = pipeline.run("如何训练", memory=memory, user_id=2)
    assert result.sources
    assert any("膝盖不适" in prompt for prompt in llm.prompts)
