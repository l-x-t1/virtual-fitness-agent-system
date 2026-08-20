from __future__ import annotations

from langchain_core.messages import AIMessage
import asyncio

from app.llm.client import LLMClient
from app.tools import FitnessToolAgent, MCPAdapter, ToolRegistry
from app.tools.venue_tool import VenueTool
from app.tools.weather_tool import WeatherTool


class Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_tool_registration_and_schema_are_complete():
    registry = ToolRegistry()
    registry.register(WeatherTool(http_get=lambda *a, **k: None).spec())
    spec = registry.get("get_weather")
    assert registry.names() == ["get_weather"]
    assert spec.parameters["required"] == ["location"]
    assert spec.parameters["properties"]["latitude"]["minimum"] == -90


def test_weather_online_result_parsing_without_real_network():
    def fake_get(url, **kwargs):
        assert kwargs["timeout"] <= 15
        if "geocoding" in url:
            return Response({"results": [{"name": "北京", "admin1": "北京市", "latitude": 39.9, "longitude": 116.4}]})
        return Response({"current": {"temperature_2m": 25.2, "relative_humidity_2m": 41, "precipitation": 0, "wind_speed_10m": 9.5, "weather_code": 1, "time": "2026-08-20T10:00"}})

    result = WeatherTool(http_get=fake_get).get_weather("北京")
    assert result["ok"] is True
    assert result["mode"] == "online"
    assert result["source"] == "open-meteo"
    assert result["data"]["temperature_c"] == 25.2
    assert result["data"]["description"] == "大致晴朗"


def test_weather_failure_is_explicit_mock_not_fake_realtime():
    def broken(*args, **kwargs):
        raise OSError("offline")

    result = WeatherTool(http_get=broken).get_weather("石家庄")
    assert result["mode"] == "mock"
    assert result["source"] == "local-weather-mock"
    assert result["data"]["is_realtime"] is False
    assert result["fallback_reason"] == "weather_service_unavailable"


def test_venue_empty_source_falls_back_to_labeled_mock():
    result = VenueTool(venue_source=lambda: []).recommend_venues("深蹲")
    assert result["ok"] is True
    assert result["mode"] == "mock"
    assert all(item["is_mock"] for item in result["data"]["venues"])


class WeatherToolLoopModel:
    def __init__(self):
        self.round = 0
        self.bound = []

    def bind_tools(self, tools, tool_choice=None):
        self.bound = tools
        return self

    def invoke(self, messages):
        self.round += 1
        if self.round == 1:
            return AIMessage(content="", tool_calls=[{"name": "get_weather", "args": {"location": "北京"}, "id": "w1"}])
        return AIMessage(content="北京天气查询完成")


def test_llm_can_select_weather_tool_through_existing_tool_loop():
    def fake_get(url, **kwargs):
        if "geocoding" in url:
            return Response({"results": [{"name": "北京", "latitude": 39.9, "longitude": 116.4}]})
        return Response({"current": {"temperature_2m": 21, "relative_humidity_2m": 50, "precipitation": 0, "wind_speed_10m": 5, "weather_code": 0, "time": "2026-08-20T10:00"}})

    registry = ToolRegistry([WeatherTool(http_get=fake_get).spec()])
    model = WeatherToolLoopModel()
    client = LLMClient(chat_model=model, environ={"LLM_PROVIDER": "deepseek"})
    result = FitnessToolAgent(registry, client).run("北京天气怎么样？")
    assert result["mode"] == "online"
    assert result["tool_results"][0]["tool"] == "get_weather"
    assert result["tool_results"][0]["result"]["mode"] == "online"
    assert model.bound


def test_mcp_unavailable_keeps_local_tools_usable(monkeypatch):
    registry = ToolRegistry([WeatherTool(http_get=lambda *a, **k: None).spec()])
    adapter = MCPAdapter(registry)
    monkeypatch.setattr("app.tools.mcp_adapter.importlib.util.find_spec", lambda name: None)
    status = adapter.status()
    assert status["mode"] == "local"
    assert status["data"]["local_tools"] == ["get_weather"]


def test_registry_turns_handler_exception_into_safe_result():
    tool = WeatherTool(http_get=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("secret stack"))).spec()
    registry = ToolRegistry([tool])
    result = registry.call("get_weather", location="北京")
    assert "secret stack" not in str(result)
    assert result["mode"] == "mock"


def test_langgraph_tool_agent_writes_tool_results_to_state(monkeypatch):
    import app.ai.langgraph_agent as workflow
    import app.tools

    class FakeToolAgent:
        def __init__(self, registry, llm_client):
            pass

        def run(self, question, context):
            return {
                "answer": "天气工具已完成",
                "tool_results": [{"tool": "get_weather", "result": {"ok": True}}],
                "mode": "fallback",
                "fallback_reason": "llm_unavailable",
            }

    monkeypatch.setattr(app.tools, "FitnessToolAgent", FakeToolAgent)
    monkeypatch.setattr(app.tools, "build_fitness_tool_registry", lambda **kwargs: object())
    update = workflow.tool_agent.__wrapped__({
        "messages": [{"role": "user", "content": "北京天气怎么样"}],
        "user_info": {"id": 7, "location": "北京"},
    })
    assert update["route"] == "report"
    assert update["tool_results"][0]["tool"] == "get_weather"
    assert update["messages"][0]["agent"] == "tool_agent"
    assert workflow._classify_request("北京天气怎么样") == "tools"
    assert workflow._classify_request("今天天气真不错") == "fallback"


def test_async_registry_and_no_api_key_startup(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    registry = ToolRegistry([WeatherTool(http_get=lambda *a, **k: (_ for _ in ()).throw(OSError())).spec()])
    result = asyncio.run(registry.acall("get_weather", location="北京"))
    assert result["mode"] == "mock"
    assert LLMClient(environ={"LLM_PROVIDER": "deepseek"}).configured is False
