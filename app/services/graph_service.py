"""
图谱服务层 — 遵循项目现有 Service 模式

被调用方:
  - 控制器 (app/controllers/graph.py)
  - 推荐 Agent (agents.py 中的 RecommendAgent)

Neo4j 可用时走图谱查询，不可用时自动回退到轻量图谱。
"""

from __future__ import annotations

import logging
from functools import lru_cache

from app.graph import GraphRAG, Neo4jFitnessGraph, is_available, run_read
from app.graph.data_import import import_all as do_import_all
from app.graph.queries import GRAPH_STATS
from app.graphrag import GraphRAGChain
from app.models.graph import (
    ExerciseRecommendItem,
    GraphImportResponse,
    GraphQueryResponse,
    GraphRecommendResponse,
    GraphSearchResponse,
    GraphStatusResponse,
    VenueRecommendItem,
)

logger = logging.getLogger("fitness.graph_service")


def _fallback_graph():
    """获取轻量图谱实例（Neo4j 不可用时的回退）"""
    from knowledge_graph import FitnessKnowledgeGraph
    g = FitnessKnowledgeGraph()
    g.refresh()
    return g


class GraphService:
    """图谱推荐服务 — Neo4j 优先，不可用时回退轻量图谱"""

    def __init__(self):
        self._rag: GraphRAG | None = None
        self._neo4j_graph: Neo4jFitnessGraph | None = None
        self._search_chain: GraphRAGChain | None = None

    @property
    def neo4j_graph(self) -> Neo4jFitnessGraph:
        if self._neo4j_graph is None:
            self._neo4j_graph = Neo4jFitnessGraph()
        return self._neo4j_graph

    @property
    def rag(self) -> GraphRAG:
        if self._rag is None:
            self._rag = GraphRAG()
        return self._rag

    @property
    def search_chain(self) -> GraphRAGChain:
        if self._search_chain is None:
            self._search_chain = GraphRAGChain()
        return self._search_chain

    # ---- 推荐接口（核心） ----

    def recommend(self, user: dict, exercise_name: str | None = None,
                  lat: float | None = None, lon: float | None = None,
                  max_distance_m: int = 80000, use_llm: bool = False,
                  top_k: int = 5) -> GraphRecommendResponse:
        """图谱推荐，Neo4j 不可用时回退轻量图谱"""

        if is_available():
            return self._recommend_neo4j(user, exercise_name, lat, lon, max_distance_m, use_llm, top_k)
        else:
            return self._recommend_fallback(user, exercise_name, top_k)

    def _recommend_neo4j(self, user, exercise_name, lat, lon, max_distance_m, use_llm, top_k):
        result = self.rag.recommend(
            user=user, exercise_name=exercise_name,
            lat=lat, lon=lon, max_distance_m=max_distance_m, use_llm=use_llm,
        )
        return GraphRecommendResponse(
            exercises=[
                ExerciseRecommendItem(
                    name=e.name, category=e.category, difficulty=e.difficulty,
                    target=e.target, equipment=e.equipment,
                    match_score=e.match_score, reason=e.reason,
                ) for e in result.exercises[:top_k]
            ],
            venues=[
                VenueRecommendItem(
                    name=v.name, location=v.location,
                    latitude=v.latitude, longitude=v.longitude,
                    crowd_index=v.crowd_index, air_quality=v.air_quality,
                    rating=v.rating, density_score=v.density_score,
                    equipment=v.equipment, capacity=v.capacity,
                    kind=v.kind, open_hours=v.open_hours,
                    distance_km=v.distance_km, match_score=v.match_score,
                ) for v in result.venues[:top_k]
            ],
        )

    def _recommend_fallback(self, user, exercise_name, top_k):
        """使用轻量图谱回退（返回真实数据，不是空）"""
        g = _fallback_graph()
        exercises = g.recommend_exercises(user)[:top_k]
        venues = g.recommend_venues(user, exercise_name)[:top_k]

        return GraphRecommendResponse(
            exercises=[
                ExerciseRecommendItem(
                    name=e.get("name", ""),
                    category=e.get("category", ""),
                    difficulty=e.get("difficulty", 1),
                    target=e.get("target", ""),
                    equipment=e.get("equipment", ""),
                    match_score=e.get("match_score", 0),
                    reason=e.get("reason", ""),
                ) for e in exercises
            ],
            venues=[
                VenueRecommendItem(
                    name=v.get("name", ""),
                    location=v.get("location", ""),
                    latitude=v.get("latitude"),
                    longitude=v.get("longitude"),
                    crowd_index=v.get("crowd_index", 50),
                    air_quality=v.get("air_quality", 50),
                    rating=v.get("rating", 4.0),
                    density_score=v.get("density_score", 0),
                    equipment=v.get("equipment", ""),
                    capacity=v.get("capacity", 0),
                    kind=v.get("kind", "outdoor"),
                    open_hours=v.get("open_hours", ""),
                    distance_km=v.get("distance_km"),
                    match_score=v.get("match_score", 0),
                ) for v in venues
            ],
        )

    def recommend_exercises(self, user, lat=None, lon=None, max_distance_m=80000):
        return self.neo4j_graph.recommend_exercises(user)

    def recommend_venues(self, user, exercise_name=None, lat=None, lon=None, max_distance_m=80000):
        return self.neo4j_graph.recommend_venues(user, exercise_name)

    # ---- 自然语言查询 ----

    def query(self, question: str) -> GraphQueryResponse:
        if is_available():
            result = self.rag.query(question)
            return GraphQueryResponse(
                question=result.query, answer=result.answer, cypher=result.cypher,
                exercises=[
                    ExerciseRecommendItem(
                        name=e.name, category=e.category, difficulty=e.difficulty,
                        target=e.target, equipment=e.equipment,
                        match_score=e.match_score, reason=e.reason,
                    ) for e in result.exercises
                ],
                venues=[
                    VenueRecommendItem(
                        name=v.name, location=v.location,
                        latitude=v.latitude, longitude=v.longitude,
                        crowd_index=v.crowd_index, air_quality=v.air_quality,
                        rating=v.rating, density_score=v.density_score,
                        equipment=v.equipment, capacity=v.capacity,
                        kind=v.kind, open_hours=v.open_hours,
                        distance_km=v.distance_km, match_score=v.match_score,
                    ) for v in result.venues
                ],
            )

        # 回退：关键词匹配
        g = _fallback_graph()
        if "场地" in question or "场馆" in question or "哪里" in question:
            venues = g.recommend_venues({"id": 1, "fitness_level": "beginner"})
            return GraphQueryResponse(
                question=question,
                answer=f"找到 {len(venues)} 个推荐场地（基于轻量图谱，安装 Neo4j 后可启用 GraphRAG 智能查询）",
                venues=[VenueRecommendItem(
                    name=v.get("name", ""), location=v.get("location", ""),
                    latitude=v.get("latitude"), longitude=v.get("longitude"),
                    crowd_index=v.get("crowd_index", 50), air_quality=v.get("air_quality", 50),
                    rating=v.get("rating", 4.0), density_score=v.get("density_score", 0),
                    equipment=v.get("equipment", ""), capacity=v.get("capacity", 0),
                    kind=v.get("kind", "outdoor"), open_hours=v.get("open_hours", ""),
                    distance_km=v.get("distance_km"), match_score=v.get("match_score", 0),
                ) for v in venues],
            )
        else:
            exercises = g.recommend_exercises({"id": 1, "fitness_level": "beginner", "preference": "综合训练"})
            return GraphQueryResponse(
                question=question,
                answer=f"找到 {len(exercises)} 个推荐动作（基于轻量图谱，安装 Neo4j 后可启用 GraphRAG 智能查询）",
                exercises=[ExerciseRecommendItem(
                    name=e.get("name", ""), category=e.get("category", ""),
                    difficulty=e.get("difficulty", 1), target=e.get("target", ""),
                    equipment=e.get("equipment", ""), match_score=e.get("match_score", 0),
                    reason=e.get("reason", ""),
                ) for e in exercises],
            )

    # ---- 状态 ----

    def search(
        self,
        query: str,
        user_id: int | None = None,
        top_k: int = 8,
        use_llm: bool = True,
    ) -> GraphSearchResponse:
        chain = self.search_chain
        chain.use_llm = use_llm
        result = chain.invoke(query, user_id=user_id, limit=top_k)
        return GraphSearchResponse(
            query=result.get("query", query),
            knowledge=result.get("knowledge", []),
            relations=result.get("relations", []),
            answer=result.get("answer", ""),
            context=result.get("context", ""),
            keywords=result.get("keywords", []),
            used_llm=bool(result.get("used_llm", False)),
        )

    def status(self) -> GraphStatusResponse:
        available = is_available()
        node_count = {}
        rel_count = 0
        if available:
            try:
                stats = run_read(GRAPH_STATS)
                if stats:
                    s = stats[0]
                    node_count = {
                        "User": s.get("user_count", 0),
                        "Exercise": s.get("exercise_count", 0),
                        "Venue": s.get("venue_count", 0),
                        "Equipment": s.get("equipment_count", 0),
                    }
                    rel_count = s.get("relationship_count", 0)
            except Exception as exc:
                logger.warning("Graph stats failed: %s", exc)

        return GraphStatusResponse(
            available=available,
            node_count=node_count,
            relationship_count=rel_count,
        )

    def import_data(self) -> dict:
        stats = do_import_all()
        return {
            "users": stats.users, "exercises": stats.exercises,
            "venues": stats.venues, "equipment": stats.equipment,
            "errors": stats.errors,
        }


@lru_cache(maxsize=1)
def get_graph_service() -> GraphService:
    return GraphService()
