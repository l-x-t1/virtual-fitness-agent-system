"""
Neo4j 向量存储 — 用 Neo4j 原生向量索引替代 FAISS

要求 Neo4j 5.x+，向量索引创建见 tools/init_graph.cypher 末尾
"""

from __future__ import annotations

import logging
from typing import Any

from app.graph.neo4j_client import is_available, run_read, run_write

logger = logging.getLogger("fitness.vector")

# 向量索引名称
VECTOR_INDEX_NAME = "exercise_embeddings"
EMBEDDING_DIM = 1536  # DeepSeek embedding 维度


def ensure_vector_index(dimension: int = EMBEDDING_DIM) -> bool:
    """创建 Neo4j 向量索引（如果不存在）"""
    if not is_available():
        return False
    try:
        run_write(
            f"""
            CREATE VECTOR INDEX {VECTOR_INDEX_NAME} IF NOT EXISTS
            FOR (e:Exercise) ON (e.embedding)
            OPTIONS {{indexConfig: {{
              `vector.dimensions`: {dimension},
              `vector.similarity_function`: 'cosine'
            }}}}
            """
        )
        return True
    except Exception as exc:
        logger.warning("Failed to create vector index: %s", exc)
        return False


def store_embedding(exercise_name: str, embedding: list[float]) -> bool:
    """存储动作的向量嵌入"""
    if not is_available():
        return False
    try:
        run_write(
            """
            MATCH (e:Exercise {name: $name})
            CALL db.create.setNodeVectorProperty(e, 'embedding', $embedding)
            RETURN e.name
            """,
            {"name": exercise_name, "embedding": embedding},
        )
        return True
    except Exception as exc:
        logger.warning("Failed to store embedding for %s: %s", exercise_name, exc)
        return False


def semantic_search(
    query_embedding: list[float],
    top_k: int = 5,
    min_score: float = 0.5,
) -> list[dict[str, Any]]:
    """语义搜索：根据查询向量找最相似的动作"""
    if not is_available():
        return []
    try:
        result = run_read(
            f"""
            CALL db.index.vector.queryNodes('{VECTOR_INDEX_NAME}', {top_k}, $embedding)
            YIELD node, score
            WHERE score >= {min_score}
            RETURN node.name AS name, node.category AS category,
                   node.difficulty AS difficulty, node.target AS target,
                   node.equipment AS equipment, node.standard_json AS standard_json,
                   ROUND(score, 4) AS similarity
            ORDER BY similarity DESC
            """,
            {"embedding": query_embedding},
        )
        return result
    except Exception as exc:
        logger.warning("Vector search failed: %s", exc)
        return []


def build_query_text(user: dict, exercise_name: str | None = None) -> str:
    """构建用于 Embedding 的查询文本（沿用原 embedding_store.py 的格式）"""
    parts = [
        f"体能水平：{user.get('fitness_level', 'beginner')}",
        f"运动偏好：{user.get('preference', '综合训练')}",
        f"伤病史：{user.get('injuries', '暂无')}",
        f"年龄：{user.get('age', 20)}",
    ]
    if exercise_name:
        parts.append(f"当前动作：{exercise_name}")
    return "；".join(parts)


def build_exercise_doc(item: dict) -> str:
    """构建动作的文档文本用于生成 Embedding"""
    standard = item.get("standard_json", "{}")
    return (
        f"动作：{item.get('name', '')}；"
        f"类别：{item.get('category', '')}；"
        f"难度：{item.get('difficulty', '')}；"
        f"目标：{item.get('target', '')}；"
        f"器材：{item.get('equipment', '')}；"
        f"标准：{standard}"
    )
