from __future__ import annotations

import math
from typing import Any, Callable

from app.llm.client import ToolSpec
from app.repositories import FitnessRepository, session_scope
from app.tools.registry import tool_result


MOCK_VENUES = [
    {
        "id": "mock-campus-gym",
        "name": "示例校园健身房",
        "location": "校园中心区（演示）",
        "kind": "indoor",
        "equipment": "跑步机、瑜伽垫、基础力量器械",
        "rating": 4.5,
        "is_mock": True,
    },
    {
        "id": "mock-park",
        "name": "示例社区公园",
        "location": "社区公园（演示）",
        "kind": "outdoor",
        "equipment": "步道、单杠、开阔场地",
        "rating": 4.2,
        "is_mock": True,
    },
]


class VenueTool:
    def __init__(self, venue_source: Callable[[], list[dict[str, Any]]] | None = None):
        self.venue_source = venue_source or self._repository_venues

    def search_venues(
        self,
        query: str = "",
        latitude: float | None = None,
        longitude: float | None = None,
        limit: int = 5,
    ) -> dict[str, Any]:
        """按名称、位置、类型或器材搜索场馆。"""
        try:
            rows = list(self.venue_source() or [])
            if not rows:
                return self._mock("venue_data_unavailable", limit)
            text = str(query or "").strip().lower()
            if text:
                rows = [item for item in rows if text in self._search_text(item)]
            rows = self._with_distance(rows, latitude, longitude)
            rows.sort(key=lambda item: (item.get("distance_km") is None, item.get("distance_km") or 0, -(item.get("rating") or 0)))
            return tool_result(
                ok=True,
                mode="online",
                source="fitness-database",
                data={"venues": rows[: self._limit(limit)]},
            )
        except Exception:
            return self._mock("venue_query_failed", limit)

    def recommend_venues(
        self,
        exercise_name: str | None = None,
        preference: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        limit: int = 5,
    ) -> dict[str, Any]:
        """根据动作、偏好和位置推荐场馆。"""
        query = " ".join(item for item in (exercise_name, preference) if item)
        result = self.search_venues("", latitude, longitude, limit=max(10, self._limit(limit)))
        venues = list(result["data"].get("venues") or [])
        if result["mode"] == "mock":
            return result
        keywords = set(query.lower().replace("、", " ").split())
        for item in venues:
            overlap = sum(1 for word in keywords if word and word in self._search_text(item))
            distance_bonus = max(0.0, 20 - float(item.get("distance_km") or 20))
            item["recommendation_score"] = round(min(100, 55 + overlap * 12 + distance_bonus), 1)
            item["reason"] = "基于现有场馆信息、训练偏好和距离的本地排序"
        venues.sort(key=lambda item: -item["recommendation_score"])
        result["data"] = {"venues": venues[: self._limit(limit)]}
        return result

    def specs(self) -> list[ToolSpec]:
        coordinate_properties = {
            "latitude": {"type": ["number", "null"], "minimum": -90, "maximum": 90},
            "longitude": {"type": ["number", "null"], "minimum": -180, "maximum": 180},
            "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5},
        }
        return [
            ToolSpec(
                name="search_venues",
                description="搜索项目数据库中的健身场馆；无真实数据时返回明确标记的 mock。",
                handler=self.search_venues,
                parameters={
                    "type": "object",
                    "properties": {"query": {"type": "string"}, **coordinate_properties},
                    "required": [],
                    "additionalProperties": False,
                },
            ),
            ToolSpec(
                name="recommend_venues",
                description="按动作、偏好和距离推荐健身场馆。",
                handler=self.recommend_venues,
                parameters={
                    "type": "object",
                    "properties": {
                        "exercise_name": {"type": ["string", "null"]},
                        "preference": {"type": ["string", "null"]},
                        **coordinate_properties,
                    },
                    "required": [],
                    "additionalProperties": False,
                },
            ),
        ]

    def _repository_venues(self) -> list[dict[str, Any]]:
        with session_scope() as session:
            return FitnessRepository(session).venues(limit=200, admin_fields=True)

    def _mock(self, reason: str, limit: int) -> dict[str, Any]:
        return tool_result(
            ok=True,
            mode="mock",
            source="local-venue-mock",
            data={"venues": [dict(item) for item in MOCK_VENUES[: self._limit(limit)]]},
            fallback_reason=reason,
        )

    def _search_text(self, item: dict[str, Any]) -> str:
        return " ".join(str(item.get(key) or "") for key in ("name", "location", "kind", "equipment", "sport_type")).lower()

    def _with_distance(self, rows: list[dict[str, Any]], latitude: Any, longitude: Any) -> list[dict[str, Any]]:
        output = []
        for row in rows:
            item = dict(row)
            try:
                item["distance_km"] = round(self._distance(float(latitude), float(longitude), float(item["latitude"]), float(item["longitude"])), 2)
            except (TypeError, ValueError, KeyError):
                item["distance_km"] = None
            output.append(item)
        return output

    def _distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        radius = 6371.0
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        d_phi = math.radians(lat2 - lat1)
        d_lambda = math.radians(lon2 - lon1)
        value = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
        return 2 * radius * math.atan2(math.sqrt(value), math.sqrt(1 - value))

    def _limit(self, value: Any) -> int:
        try:
            return max(1, min(int(value), 20))
        except (TypeError, ValueError):
            return 5
