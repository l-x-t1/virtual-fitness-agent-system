from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

import httpx

from app.llm.client import ToolSpec
from app.tools.registry import tool_result


WEATHER_CODES = {
    0: "晴",
    1: "大致晴朗",
    2: "局部多云",
    3: "阴",
    45: "雾",
    48: "雾凇",
    51: "小毛毛雨",
    53: "毛毛雨",
    55: "较强毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    80: "阵雨",
    81: "较强阵雨",
    82: "强阵雨",
    95: "雷暴",
}


class WeatherTool:
    def __init__(self, http_get: Callable[..., Any] | None = None, timeout: float = 6.0):
        self.http_get = http_get or httpx.get
        self.timeout = max(1.0, min(float(timeout), 15.0))

    def get_weather(
        self,
        location: str,
        latitude: float | None = None,
        longitude: float | None = None,
    ) -> dict[str, Any]:
        """查询指定地点的当前天气，可选传入纬度和经度。"""
        place = str(location or "当前位置").strip()[:120] or "当前位置"
        try:
            lat, lon, resolved = self._coordinates(place, latitude, longitude)
            response = self.http_get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m,weather_code",
                    "timezone": "auto",
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
            current = payload.get("current") or {}
            code = int(current.get("weather_code", -1))
            data = {
                "location": resolved,
                "latitude": lat,
                "longitude": lon,
                "temperature_c": self._number(current.get("temperature_2m")),
                "humidity_percent": self._number(current.get("relative_humidity_2m")),
                "precipitation_mm": self._number(current.get("precipitation")),
                "wind_speed_kmh": self._number(current.get("wind_speed_10m")),
                "description": WEATHER_CODES.get(code, "未知天气"),
                "observed_at": current.get("time"),
            }
            if data["temperature_c"] is None or not data["observed_at"]:
                raise ValueError("incomplete_weather_payload")
            return tool_result(ok=True, mode="online", source="open-meteo", data=data)
        except Exception:
            return tool_result(
                ok=True,
                mode="mock",
                source="local-weather-mock",
                data=self._mock(place, latitude, longitude),
                fallback_reason="weather_service_unavailable",
            )

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="get_weather",
            description="查询训练地点的当前天气；网络不可用时返回明确标记的 mock 数据。",
            handler=self.get_weather,
            parameters={
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "城市、区域或地点名称"},
                    "latitude": {"type": ["number", "null"], "minimum": -90, "maximum": 90},
                    "longitude": {"type": ["number", "null"], "minimum": -180, "maximum": 180},
                },
                "required": ["location"],
                "additionalProperties": False,
            },
        )

    def _coordinates(self, location: str, latitude: Any, longitude: Any) -> tuple[float, float, str]:
        if latitude is not None and longitude is not None:
            return float(latitude), float(longitude), location
        response = self.http_get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": location, "count": 1, "language": "zh", "format": "json"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        results = (response.json() or {}).get("results") or []
        if not results:
            raise ValueError("location_not_found")
        item = results[0]
        resolved = str(item.get("name") or location)
        if item.get("admin1"):
            resolved = f"{resolved}，{item['admin1']}"
        return float(item["latitude"]), float(item["longitude"]), resolved

    def _mock(self, location: str, latitude: Any, longitude: Any) -> dict[str, Any]:
        return {
            "location": location,
            "latitude": self._number(latitude),
            "longitude": self._number(longitude),
            "temperature_c": 22.0,
            "humidity_percent": 50.0,
            "precipitation_mm": 0.0,
            "wind_speed_kmh": 8.0,
            "description": "演示天气（非实时）",
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "is_realtime": False,
        }

    def _number(self, value: Any) -> float | None:
        try:
            return round(float(value), 2) if value is not None else None
        except (TypeError, ValueError):
            return None
