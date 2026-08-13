from __future__ import annotations

import json
from pathlib import Path

from app.embeddings import SemanticEmbeddings
from tools.evaluate_semantic_recall import LegacyLexicalEmbeddings, evaluate


def test_semantic_embeddings_follow_langchain_protocol():
    embeddings = SemanticEmbeddings(allow_fallback=True)
    docs = embeddings.embed_documents(["膝盖不适低冲击训练", "核心稳定平板支撑"])
    query = embeddings.embed_query("保护膝盖")
    assert len(docs) == 2
    assert len(query) == len(docs[0])
    assert embeddings.backend in {"sentence-transformers", "offline-lexical"}


def test_semantic_recall_beats_or_matches_legacy_lexical():
    cases = json.loads(
        Path("tests/fixtures/fitness_semantic_recall_cases.json").read_text(encoding="utf-8")
    )
    legacy = evaluate(cases, LegacyLexicalEmbeddings(), top_k=3)
    semantic = evaluate(cases, SemanticEmbeddings(allow_fallback=True), top_k=3)
    assert len(cases) == 25
    assert semantic["recall_at_k"] >= legacy["recall_at_k"]
    assert semantic["recall_at_k"] >= 0.8
