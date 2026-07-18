"""
Neo4j 健身知识图谱 — 与 knowledge_graph.FitnessKnowledgeGraph 接口完全兼容

用途：作为 RecommendAgent 中 self.graph 的替换实现

Neo4j 不可用时，回退到原 FitnessKnowledgeGraph。
"""

from __future__ import annotations

import logging
from typing import Any

from app.graph import is_available
from app.graph.graphrag import GraphRAG

logger = logging.getLogger("fitness.neo4j_graph")

DEFAULT_LAT = 38.047
DEFAULT_LON = 114.514


class Neo4jFitnessGraph:
    """
    基于 Neo4j 的知识图谱推荐引擎。

    接口完全兼容 knowledge_graph.FitnessKnowledgeGraph，
    但查询走 Neo4j Cypher 而非内存遍历。

    Neo4j 不可用时，回退到原 FitnessKnowledgeGraph。
    """

    def __init__(self):
        self._rag: GraphRAG | None = None
        self._fallback = None
        self.exercises: list[dict] = []
        self.venues: list[dict] = []

    # ---- 兼容 FitnessKnowledgeGraph 的公开接口 ----

    def refresh(self):
        """加载数据"""
        if is_available():
            from app.graph.neo4j_client import run_read
            try:
                ex_rows = run_read("MATCH (e:Exercise) RETURN e ORDER BY e.difficulty")
                self.exercises = [
                    {k: v for k, v in row.get("e", {}).items() if not k.startswith("embedding")}
                    for row in ex_rows
                ]
                v_rows = run_read("MATCH (v:Venue) RETURN v ORDER BY v.crowd_index, v.air_quality")
                self.venues = [row.get("v", {}) for row in v_rows]
            except Exception:
                self._load_fallback()
        else:
            self._load_fallback()

    def _load_fallback(self):
        try:
            from app.repositories import FitnessRepository, session_scope
            with session_scope() as session:
                repo = FitnessRepository(session)
                self.exercises = repo.exercises()
                self.venues = repo.venues()
        except Exception:
            self.exercises = []
            self.venues = []

    def recommend_exercises(self, user: dict[str, Any]) -> list[dict[str, Any]]:
        if is_available():
            try:
                return self.rag.recommend_exercises_for_user(
                    user=user, lat=self._lat(user), lon=self._lon(user)
                )
            except Exception as exc:
                logger.warning("Neo4j rec failed: %s", exc)
        return self._fallback_recommend_exercises(user)

    def recommend_venues(
        self,
        user: dict[str, Any],
        exercise_name: str | None = None,
    ) -> list[dict[str, Any]]:
        if is_available():
            try:
                return self.rag.recommend_venues_for_user(
                    user=user, exercise_name=exercise_name,
                    lat=self._lat(user), lon=self._lon(user),
                )
            except Exception as exc:
                logger.warning("Neo4j venue failed: %s", exc)
        return self._fallback_recommend_venues(user, exercise_name)

    # ---- 回退 ----

    def _fallback_recommend_exercises(self, user: dict) -> list[dict]:
        fb = self._get_fallback()
        if fb:
            fb.refresh()
            return fb.recommend_exercises(user)
        return []

    def _fallback_recommend_venues(self, user: dict, exercise_name: str | None = None) -> list[dict]:
        fb = self._get_fallback()
        if fb:
            fb.refresh()
            return fb.recommend_venues(user, exercise_name)
        return []

    def _get_fallback(self):
        if self._fallback is None:
            try:
                from knowledge_graph import FitnessKnowledgeGraph
                self._fallback = FitnessKnowledgeGraph()
            except ImportError:
                self._fallback = False
        return self._fallback if self._fallback is not False else None

    # ---- 工具 ----

    @property
    def rag(self) -> GraphRAG:
        if self._rag is None:
            self._rag = GraphRAG()
        return self._rag

    @staticmethod
    def _lat(u): return float(u.get("current_lat") or u.get("latitude") or DEFAULT_LAT)

    @staticmethod
    def _lon(u): return float(u.get("current_lon") or u.get("longitude") or DEFAULT_LON)
