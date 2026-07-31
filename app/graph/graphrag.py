"""
LangChain GraphRAG 封装类 — GraphCypherQAChain + 语义搜索

核心能力:
  1. 自然语言 → Cypher 查询（LangChain GraphCypherQAChain）
  2. 图谱遍历推荐（按用户画像/目标/场地/器材）
  3. 混合检索：图谱结果 + 向量语义搜索 → LLM 融合排序

使用示例:
  rag = GraphRAG()
  result = rag.query("推荐适合膝盖不好的新手的下肢训练")
  rec = rag.recommend(user_dict, exercise_name="深蹲")
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.graph.neo4j_client import is_available, run_read
from app.graph.queries import (
    RECOMMEND_BY_BODY_PART,
    RECOMMEND_BY_GOAL,
    RECOMMEND_BY_VENUE,
    RECOMMEND_HYBRID,
    RECOMMEND_VENUES,
    RECOMMEND_WITH_RISK_FILTER,
    resolve_risky_body_parts,
)
from app.graph.schemas import (
    GraphExercise,
    GraphRAGResult,
    GraphRecommendationResult,
    GraphVenue,
)

logger = logging.getLogger("fitness.graphrag")

# ============================================================
# 尝试导入 LangChain，未安装时降级
# ============================================================
try:
    from langchain_community.chains.graph_qa.cypher import GraphCypherQAChain
    from langchain_community.graphs import Neo4jGraph as LangChainNeo4jGraph
    from app.llm.client import LLMClient

    _HAS_LANGCHAIN = True
except ImportError:
    _HAS_LANGCHAIN = False
    logger.warning("langchain_community not available; GraphRAG LLM features disabled.")


# ============================================================
# Neo4j → LangChain 图适配
# ============================================================

class _Neo4jGraphAdapter:
    """将 neo4j 原生 driver 适配为 LangChain 的 Graph 接口"""

    def __init__(self):
        from app.core.config import settings

        self.url = settings.neo4j_uri
        self.username = settings.neo4j_username
        self.password = settings.neo4j_password
        self.database = settings.neo4j_database

    def query(self, cypher: str, params: dict | None = None) -> list[dict]:
        return run_read(cypher, params)

    def refresh_schema(self) -> str:
        """自动提取图谱 Schema 给 LLM"""
        try:
            nodes = run_read("CALL db.labels()")
            relationships = run_read("CALL db.relationshipTypes()")

            node_list = []
            for record in nodes:
                label = record.get("label", "")
                if label:
                    # 取每个标签的 1 个样例节点来获取属性名
                    props = run_read(
                        f"MATCH (n:`{label}`) RETURN n LIMIT 1"
                    )
                    if props:
                        sample = props[0].get("n", {})
                        if isinstance(sample, dict):
                            prop_names = [k for k in sample if not k.startswith("embedding")]
                            node_list.append(f":{label} {{{', '.join(prop_names[:10])}}}")

            rel_list = [r.get("relationshipType", "") for r in relationships if r.get("relationshipType")]

            return (
                "Node types:\n" + "\n".join(f"  {n}" for n in node_list) +
                "\nRelationship types:\n" + "\n  ".join(rel_list)
            )
        except Exception:
            return "Schema unavailable"


# ============================================================
# GraphRAG 主类
# ============================================================

class GraphRAG:
    """
    Neo4j 图谱 + 语义搜索的推荐引擎

    两种工作模式:
      - LLM 模式: 使用 GraphCypherQAChain，自然语言 → Cypher → 答案
      - 规则模式: 使用预定义 Cypher 模板，确定性推荐
    """

    def __init__(self, llm_client=None):
        self._chain = None
        self._llm = llm_client
        self._adapter = None

    # ---- 内部初始化 ----

    @property
    def adapter(self) -> _Neo4jGraphAdapter:
        if self._adapter is None:
            self._adapter = _Neo4jGraphAdapter()
        return self._adapter

    def _get_chain(self) -> GraphCypherQAChain | None:
        """懒加载 GraphCypherQAChain"""
        if not _HAS_LANGCHAIN or not is_available():
            return None
        if self._chain is not None:
            return self._chain

        try:
            if self._llm is None:
                self._llm = LLMClient()

            # 使用 LangChain 的 Neo4jGraph 包装
            lc_graph = LangChainNeo4jGraph(
                url=self.adapter.url,
                username=self.adapter.username,
                password=self.adapter.password,
                database=self.adapter.database,
            )

            self._chain = GraphCypherQAChain.from_llm(
                llm=self._llm,
                graph=lc_graph,
                verbose=False,
                validate_cypher=True,
                top_k=10,
                return_direct=True,
                return_intermediate_steps=True,
            )
            return self._chain
        except Exception as exc:
            logger.warning("Failed to init GraphCypherQAChain: %s", exc)
            return None

    # ---- 公开接口 ----

    def query(self, question: str) -> GraphRAGResult:
        """
        自然语言查询图谱（LLM 模式）
        例: "什么动作适合膝盖受伤的新手？"
        """
        if not is_available():
            return GraphRAGResult(query=question, answer="Neo4j 不可用，请检查服务状态")

        chain = self._get_chain()
        if chain is None:
            return self._fallback_query(question)

        try:
            raw = chain.invoke({"query": question})
            answer = str(raw.get("result", ""))
            cypher = ""
            if "intermediate_steps" in raw and raw["intermediate_steps"]:
                cypher = str(raw["intermediate_steps"][-1].get("query", ""))
            return GraphRAGResult(query=question, answer=answer, cypher=cypher)
        except Exception as exc:
            logger.warning("GraphCypherQAChain failed: %s", exc)
            return self._fallback_query(question)

    def recommend(
        self,
        user: dict,
        exercise_name: str | None = None,
        lat: float | None = None,
        lon: float | None = None,
        max_distance_m: int = 80000,
        use_llm: bool = False,
    ) -> GraphRecommendationResult:
        """
        混合推荐：图谱规则 + 可选 LLM 融合

        Args:
            user: 用户 dict（含 user_id, fitness_level, preference, injuries, location 等）
            exercise_name: 当前动作名（可选，用于场地推荐时匹配器材）
            lat/lon: 用户当前坐标，不传则根据 location 估算
            max_distance_m: 场地搜索半径（米），默认 80km
            use_llm: 是否启用 LLM 对结果进行语义排序

        Returns:
            GraphRecommendationResult(exercises=[...], venues=[...])
        """
        if not is_available():
            logger.info("Neo4j not available; falling back to empty result")
            return GraphRecommendationResult()

        user_id = user.get("id", user.get("user_id", 0))
        lat = lat or self._resolve_lat(user)
        lon = lon or self._resolve_lon(user)
        risky = resolve_risky_body_parts(user.get("injuries"))

        # 1. 图谱规则推荐动作（含伤病风险降权）
        exercises = self._recommend_exercises_internal(
            user_id=user_id, lat=lat, lon=lon, max_distance_m=max_distance_m, risky_body_parts=risky,
        )

        # 2. 图谱规则推荐场地
        venues = self._recommend_venues_internal(
            user_id=user_id, exercise_name=exercise_name,
            lat=lat, lon=lon, max_distance_m=max_distance_m,
        )

        # 3. 可选 LLM 融合排序
        if use_llm and exercises:
            exercises = self._llm_rerank_exercises(user, exercises)

        return GraphRecommendationResult(exercises=exercises, venues=venues)

    def recommend_exercises_for_user(
        self,
        user: dict,
        lat: float | None = None,
        lon: float | None = None,
        max_distance_m: int = 80000,
    ) -> list[dict]:
        """按用户画像推荐动作（兼容 FitnessKnowledgeGraph 接口）"""
        user_id = user.get("id", user.get("user_id", 0))
        lat = lat or self._resolve_lat(user)
        lon = lon or self._resolve_lon(user)
        risky = resolve_risky_body_parts(user.get("injuries"))

        exercises = self._recommend_exercises_internal(
            user_id=user_id, lat=lat, lon=lon, max_distance_m=max_distance_m, risky_body_parts=risky
        )
        return [
            {
                "name": e.name,
                "category": e.category,
                "difficulty": e.difficulty,
                "target": e.target,
                "equipment": e.equipment,
                "match_score": e.match_score,
                "reason": e.reason,
            }
            for e in exercises
        ]

    def recommend_venues_for_user(
        self,
        user: dict,
        exercise_name: str | None = None,
        lat: float | None = None,
        lon: float | None = None,
        max_distance_m: int = 80000,
    ) -> list[dict]:
        """按用户位置和动作需求推荐场地（兼容 FitnessKnowledgeGraph 接口）"""
        user_id = user.get("id", user.get("user_id", 0))
        lat = lat or self._resolve_lat(user)
        lon = lon or self._resolve_lon(user)

        venues = self._recommend_venues_internal(
            user_id=user_id, exercise_name=exercise_name,
            lat=lat, lon=lon, max_distance_m=max_distance_m,
        )
        return [
            {
                "name": v.name,
                "location": v.location,
                "latitude": v.latitude,
                "longitude": v.longitude,
                "crowd_index": v.crowd_index,
                "air_quality": v.air_quality,
                "rating": v.rating,
                "density_score": v.density_score,
                "equipment": v.equipment,
                "capacity": v.capacity,
                "kind": v.kind,
                "open_hours": v.open_hours,
                "distance_km": v.distance_km,
                "match_score": v.match_score,
            }
            for v in venues
        ]

    # ---- 内部实现 ----

    def _recommend_exercises_internal(
        self, user_id: int, lat: float, lon: float, max_distance_m: int,
        risky_body_parts: list[str] | None = None,
    ) -> list[GraphExercise]:
        """内部：执行混合查询获取动作推荐（支持风险感知过滤）"""
        # 有伤病部位时，优先走风险感知查询（RISK 关系降权）
        if risky_body_parts:
            try:
                rows = run_read(
                    RECOMMEND_WITH_RISK_FILTER,
                    {"user_id": user_id, "risky_body_parts": risky_body_parts, "limit": 5},
                )
                if rows:
                    return self._exercise_rows_to_models(rows)
            except Exception as exc:
                logger.warning("Risk-filtered query failed: %s", exc)

        try:
            rows = run_read(
                RECOMMEND_HYBRID,
                {
                    "user_id": user_id,
                    "lat": lat,
                    "lon": lon,
                    "max_distance_m": max_distance_m,
                    "limit": 5,
                },
            )
            if rows:
                return self._exercise_rows_to_models(rows)
        except Exception as exc:
            logger.warning("Hybrid query failed: %s", exc)

        # 回退：仅按目标推荐
        try:
            rows = run_read(RECOMMEND_BY_GOAL, {"user_id": user_id, "limit": 5})
            return self._exercise_rows_to_models(rows)
        except Exception as exc:
            logger.warning("Goal-based query failed: %s", exc)

        return []

    @staticmethod
    def _exercise_rows_to_models(rows: list[dict]) -> list[GraphExercise]:
        return [
            GraphExercise(
                name=row.get("name", ""),
                category=row.get("category", ""),
                difficulty=row.get("difficulty", 1),
                target=row.get("target", ""),
                equipment=row.get("equipment", ""),
                match_score=float(row.get("match_score", 0)),
                reason=row.get("reason", ""),
            )
            for row in rows
        ]

    def _recommend_venues_internal(
        self, user_id: int, exercise_name: str | None,
        lat: float, lon: float, max_distance_m: int,
    ) -> list[GraphVenue]:
        """内部：按位置和器材需求推荐场地"""
        try:
            rows = run_read(
                RECOMMEND_VENUES,
                {
                    "user_id": user_id,
                    "exercise_name": exercise_name or "",
                    "lat": lat,
                    "lon": lon,
                    "max_distance_m": max_distance_m,
                    "limit": 5,
                },
            )
            return [
                GraphVenue(
                    name=row.get("name", ""),
                    location=row.get("location", ""),
                    latitude=row.get("latitude"),
                    longitude=row.get("longitude"),
                    crowd_index=row.get("crowd_index", 50),
                    air_quality=row.get("air_quality", 50),
                    rating=row.get("rating", 4.0),
                    density_score=row.get("density_score", 0.0),
                    equipment=row.get("equipment", ""),
                    capacity=row.get("capacity", 0),
                    kind=row.get("kind", "outdoor"),
                    open_hours=row.get("open_hours", ""),
                    distance_km=row.get("distance_km"),
                    match_score=float(row.get("match_score", 0)),
                )
                for row in rows
            ]
        except Exception as exc:
            logger.warning("Venue recommendation failed: %s", exc)
            return []

    def _llm_rerank_exercises(
        self, user: dict, exercises: list[GraphExercise]
    ) -> list[GraphExercise]:
        """使用 LLM 对推荐结果进行语义重排"""
        if self._llm is None:
            try:
                from app.llm.client import LLMClient
                self._llm = LLMClient()
            except Exception:
                return exercises
        try:
            prompt = self._build_rerank_prompt(user, exercises)
            response = self._llm.invoke(prompt)
            reranked = self._parse_rerank_response(response, exercises)
            return reranked if reranked else exercises
        except Exception as exc:
            logger.info("LLM rerank skipped: %s", exc)
            return exercises

    def _build_rerank_prompt(self, user: dict, exercises: list[GraphExercise]) -> str:
        risky_parts = resolve_risky_body_parts(user.get("injuries"))
        risk_note = f"，高风险部位={','.join(risky_parts)}" if risky_parts else ""
        return "\n".join([
            "将下列候选动作为用户重新排序，返回 JSON 数组（按适合度从高到低，最多5个）。",
            f"用户画像：体能={user.get('fitness_level','')}，偏好={user.get('preference','')}，伤病史={user.get('injuries','')}{risk_note}",
            "注意：对伤病史中涉及的部位，降低对应动作的优先级。",
            "候选动作：",
            json.dumps([
                {"name": e.name, "category": e.category, "difficulty": e.difficulty,
                 "target": e.target, "equipment": e.equipment, "score": e.match_score}
                for e in exercises
            ], ensure_ascii=False),
            '返回格式：{"recommendations": [{"name": "...", "reason": "...", "score": 0.0}]}',
        ])

    def _parse_rerank_response(
        self, response: str, originals: list[GraphExercise]
    ) -> list[GraphExercise]:
        try:
            data = json.loads(response)
        except json.JSONDecodeError:
            # 尝试提取 JSON
            import re
            match = re.search(r'\{[\s\S]*\}', response)
            if match:
                try:
                    data = json.loads(match.group())
                except json.JSONDecodeError:
                    return []
            else:
                return []

        items = data.get("recommendations", [])
        by_name = {e.name: e for e in originals}
        result = []
        for item in items:
            name = item.get("name", "")
            if name in by_name:
                existing = by_name[name]
                existing.match_score = float(item.get("score", existing.match_score))
                existing.reason = item.get("reason", existing.reason)
                result.append(existing)
        return result[:5]

    def fallback_query(self, question: str) -> GraphRAGResult:
        """无 LLM 时的回退查询"""
        return self._fallback_query(question)

    def _fallback_query(self, question: str) -> GraphRAGResult:
        """基于关键词的简单图谱搜索"""
        results: list[GraphExercise] = []
        cypher = ""

        # 关键词匹配
        if "场地" in question or "场馆" in question or "哪里" in question:
            try:
                rows = run_read("MATCH (v:Venue) RETURN v LIMIT 5")
                for row in rows:
                    v = row.get("v", {})
                    results.append(GraphExercise(
                        name=v.get("name", ""),
                        category="场地",
                        reason=v.get("location", ""),
                    ))
                cypher = "MATCH (v:Venue) RETURN v LIMIT 5"
            except Exception:
                pass
        else:
            try:
                rows = run_read(
                    "MATCH (e:Exercise) RETURN e.name AS name, e.category AS category, "
                    "e.target AS target, e.equipment AS equipment LIMIT 5"
                )
                for row in rows:
                    results.append(GraphExercise(
                        name=row.get("name", ""),
                        category=row.get("category", ""),
                        target=row.get("target", ""),
                        equipment=row.get("equipment", ""),
                        reason="全部动作列表",
                    ))
                cypher = "MATCH (e:Exercise) RETURN e LIMIT 5"
            except Exception:
                pass

        return GraphRAGResult(
            query=question,
            answer=f"找到 {len(results)} 条结果（基于关键词匹配，未使用 LLM）",
            cypher=cypher,
            exercises=results,
        )

    # ---- 坐标解析 ----

    @staticmethod
    def _resolve_lat(user: dict) -> float:
        if user.get("current_lat"):
            return float(user["current_lat"])
        if user.get("latitude"):
            return float(user["latitude"])
        return 38.047  # 石家庄默认纬度

    @staticmethod
    def _resolve_lon(user: dict) -> float:
        if user.get("current_lon"):
            return float(user["current_lon"])
        if user.get("longitude"):
            return float(user["longitude"])
        return 114.514  # 石家庄默认经度
