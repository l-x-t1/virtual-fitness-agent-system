from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import agents
import pytest

from app.agents import (
    EvaluateAgent,
    MotivationAgent,
    ProfileAgent,
    RecommendAgent,
    ReportAgent,
)
from app.agents.embedding_store import ExerciseVectorStore
from app.agents.mediapipe_adapter import MediaPipeAdapter
from app.agents.output_parser import LLMOutputError, OutputParser
from app.agents.schemas import (
    EvaluateOutput,
    MotivationOutput,
    ProfileOutput,
    RecommendOutput,
    ReportOutput,
)
from app.llm import LLMClient, LLMInvocationError


class FakeLLM:
    def __init__(self, response: dict | str):
        self.response = response
        self.config = SimpleNamespace(provider="fake", model="fake-model")
        self.async_calls = 0

    def invoke(self, prompt: str) -> str:
        return self._response()

    async def ainvoke(self, prompt: str) -> str:
        self.async_calls += 1
        return self._response()

    def _response(self) -> str:
        if isinstance(self.response, str):
            return self.response
        return json.dumps(self.response, ensure_ascii=False)


class ToolLoopModel:
    def __init__(self, responses):
        self.responses = list(responses)
        self.bound_tools = []
        self.tool_choice = None
        self.invocations = []

    def bind_tools(self, tools, tool_choice=None):
        self.bound_tools = list(tools)
        self.tool_choice = tool_choice
        return self

    def invoke(self, prompt):
        self.invocations.append(prompt)
        return self.responses.pop(0)

    async def ainvoke(self, prompt):
        self.invocations.append(prompt)
        return self.responses.pop(0)


def user() -> dict:
    return {
        "nickname": "小林",
        "fitness_level": "beginner",
        "goals": ["提升核心稳定"],
        "preference": "低冲击",
        "injuries": "膝盖偶尔不适",
    }


def knowledge_base() -> list[dict]:
    return [
        {
            "name": "平板支撑",
            "category": "核心训练",
            "difficulty": 1,
            "target": "核心稳定",
            "equipment": "瑜伽垫",
        },
        {
            "name": "开合跳",
            "category": "有氧训练",
            "difficulty": 2,
            "target": "心肺耐力",
            "equipment": "徒手",
        },
    ]


def history() -> list[dict]:
    return [
        {"exercise_name": "深蹲", "score": 70, "duration": 20},
        {"exercise_name": "平板支撑", "score": 90, "duration": 25},
    ]


def test_deepseek_configuration_parsing():
    client = LLMClient(
        environ={
            "LLM_PROVIDER": "deepseek",
            "MODEL_NAME": "deepseek-v4-flash",
            "DEEPSEEK_API_KEY": "deepseek-test-secret",
            "DEEPSEEK_BASE_URL": "https://api.deepseek.com/",
        }
    )
    assert client.config.provider == "deepseek"
    assert client.config.model == "deepseek-v4-flash"
    assert client.config.base_url == "https://api.deepseek.com"
    assert client.config.configured is True
    assert "deepseek-test-secret" not in repr(client.config)


def test_dashscope_configuration_parsing():
    client = LLMClient(
        environ={
            "LLM_PROVIDER": "dashscope",
            "MODEL_NAME": "qwen-plus",
            "DASHSCOPE_API_KEY": "dashscope-test-secret",
            "DASHSCOPE_BASE_URL": "",
        }
    )
    assert client.config.provider == "dashscope"
    assert client.config.model == "qwen-plus"
    assert client.config.base_url == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert client.config.configured is True


def test_missing_api_key_returns_explicit_fallback():
    client = LLMClient(environ={"LLM_PROVIDER": "deepseek", "DEEPSEEK_API_KEY": ""})
    result = ProfileAgent(llm_client=client).summarize(user())
    assert result["mode"] == "fallback"
    assert result["fallback_reason"] == "missing_or_invalid_llm_configuration"
    ProfileOutput.model_validate({"profile": result["profile"]})


def test_markdown_code_block_json_is_parsed():
    raw = """```json
    {"profile":{"fitness_level":"beginner","goals":[],"preferences":[],"risk_flags":[],"habits":[],"summary":"信息有限"}}
    ```"""
    parsed = OutputParser().parse(raw, ProfileOutput)
    assert parsed["profile"]["fitness_level"] == "beginner"


def test_invalid_json_has_clear_error_and_agent_falls_back():
    with pytest.raises(LLMOutputError, match="JSON"):
        OutputParser().loads("not-json")
    result = ProfileAgent(llm_client=FakeLLM("not-json")).summarize(user())
    assert result["mode"] == "fallback"
    assert result["fallback_reason"] == "invalid_model_output"


def test_profile_agent_structured_online_output():
    response = {
        "profile": {
            "fitness_level": "beginner",
            "goals": ["提升核心稳定"],
            "preferences": ["低冲击"],
            "risk_flags": ["输入记录膝盖偶尔不适"],
            "habits": ["每周两次"],
            "summary": "适合循序渐进的低冲击核心训练。",
        }
    }
    result = ProfileAgent(llm_client=FakeLLM(response)).summarize(user())
    assert result["mode"] == "online"
    ProfileOutput.model_validate({"profile": result["profile"]})


def test_recommend_agent_filters_actions_outside_knowledge_base():
    fake = FakeLLM(
        {
            "recommendations": [
                {"name": "不存在动作", "score": 99, "reason": "编造", "risk_warning": ""},
                {
                    "name": "平板支撑",
                    "score": 91,
                    "reason": "匹配核心稳定目标",
                    "risk_warning": "",
                },
            ]
        }
    )
    store = ExerciseVectorStore()
    result = RecommendAgent(llm_client=fake, vector_store=store).recommend(
        user(), knowledge_base()
    )
    assert [item["name"] for item in result["recommendations"]] == ["平板支撑"]
    assert result["retrieval_backend"] == "local"
    RecommendOutput.model_validate({"recommendations": result["recommendations"]})


def test_local_retrieval_fallback_is_deterministic():
    store = ExerciseVectorStore()
    first = store.search(user(), knowledge_base(), top_k=2)
    second = store.search(user(), knowledge_base(), top_k=2)
    assert first == second
    assert store.last_backend == "local"
    assert {item["name"] for item in first} <= {"平板支撑", "开合跳"}


def test_chroma_failure_uses_local_semantic_retrieval(monkeypatch):
    store = ExerciseVectorStore()

    def unavailable(*args, **kwargs):
        raise RuntimeError("chroma unavailable")

    monkeypatch.setattr(store, "_sync_chroma", unavailable)
    results = store.search(user(), knowledge_base(), top_k=1)
    assert len(results) == 1
    assert store.last_backend == "local"


def test_mediapipe_landmarks_compute_angles_and_availability():
    landmarks = [{"x": 0.0, "y": 0.0, "visibility": 0.0} for _ in range(33)]
    coordinates = {
        11: (0.0, 0.0),
        12: (2.0, 0.02),
        23: (0.0, 1.0),
        24: (2.0, 1.0),
        25: (0.0, 2.0),
        26: (2.0, 2.0),
        27: (1.0, 2.0),
        28: (3.0, 2.0),
    }
    for index, (x, y) in coordinates.items():
        landmarks[index] = {"x": x, "y": y, "visibility": 1.0}
    features = MediaPipeAdapter().to_features({"landmarks": landmarks})
    assert features["angle"]["knee"] == pytest.approx(90.0)
    assert features["angle"]["hip"] == pytest.approx(180.0, abs=0.1)
    assert features["angle"]["shoulder_balance"] == pytest.approx(2.0)
    assert {"knee", "hip", "shoulder_balance"} <= set(features["available_features"])


def test_evaluate_agent_does_not_invent_missing_keypoint_errors():
    fake = FakeLLM(
        {
            "evaluation": {
                "score": 75,
                "mistakes": ["膝盖内扣", "髋部偏移"],
                "suggestions": ["调整膝盖与髋部"],
                "risk_level": "high",
            }
        }
    )
    result = EvaluateAgent(llm_client=fake).evaluate("深蹲", 75, None)
    assert result["evaluation"]["mistakes"] == []
    assert result["evaluation"]["risk_level"] == "unknown"
    EvaluateOutput.model_validate({"evaluation": result["evaluation"]})


def test_motivation_agent_structured_output():
    response = {
        "message": "小林，本次完成20分钟并取得86分。",
        "story": "你点亮了森林关卡的新路标。",
        "strategy": "下次继续优先保持动作质量。",
        "next_goal": "完成20分钟并达到88分。",
    }
    result = MotivationAgent(llm_client=FakeLLM(response)).settle(
        user(), 86, 20, points=20, level=2, unlocked_levels=["森林关卡"]
    )
    assert result["mode"] == "online"
    MotivationOutput.model_validate(
        {key: result[key] for key in ("message", "story", "strategy", "next_goal")}
    )


@pytest.mark.parametrize("report_type", ["weekly", "monthly"])
def test_weekly_and_monthly_reports(report_type):
    client = LLMClient(environ={"LLM_PROVIDER": "dashscope", "DASHSCOPE_API_KEY": ""})
    result = ReportAgent(llm_client=client).build_report(history(), report_type)
    assert result["report_type"] == report_type
    assert result["training_count"] == 2
    assert result["average_score"] == 80
    assert result["total_duration"] == 45
    assert result["mode"] == "fallback"
    ReportOutput.model_validate(
        {key: value for key, value in result.items() if key in ReportOutput.model_fields}
    )


def test_empty_report_is_explicit():
    result = ReportAgent(llm_client=FakeLLM({})).build_report([], "monthly")
    assert result["empty"] is True
    assert result["training_count"] == 0
    assert result["mode"] == "fallback"
    assert result["fallback_reason"] == "no_training_records"


def test_report_agent_enforces_computed_numbers_and_real_action_names():
    response = {
        "report_type": "weekly",
        "empty": False,
        "training_count": 999,
        "average_score": 100,
        "total_duration": 999,
        "strengths": ["虚构动作"],
        "weaknesses": ["深蹲"],
        "trend_analysis": "近期表现有所变化。",
        "risk_reminders": [],
        "next_plan": ["下周训练两次"],
        "summary": "本周训练总结。",
    }
    result = ReportAgent(llm_client=FakeLLM(response)).build_report(history(), "weekly")
    assert result["training_count"] == 2
    assert result["average_score"] == 80
    assert result["total_duration"] == 45
    assert "虚构动作" not in result["strengths"]


def test_llmclient_tool_loop_supports_multiple_tool_calls():
    tool_calls = []

    def recommend_exercises(profile, top_k=5):
        tool_calls.append(("recommend_exercises", profile["fitness_level"], top_k))
        return {
            "exercises": [
                {"name": "平板支撑", "score": 92, "reason": "tool", "risk_warning": ""},
                {"name": "深蹲", "score": 88, "reason": "tool", "risk_warning": ""},
            ]
        }

    def recommend_venues(profile, exercise_name=None):
        tool_calls.append(("recommend_venues", exercise_name))
        return {"venues": [{"name": "校内健身房", "match_score": 90}]}

    model = ToolLoopModel(
        [
            SimpleNamespace(
                content=json.dumps(
                    {
                        "tool_call": "recommend_exercises",
                        "arguments": {"profile": user(), "top_k": 2},
                    },
                    ensure_ascii=False,
                )
            ),
            SimpleNamespace(
                content=json.dumps(
                    {
                        "tool_call": "recommend_venues",
                        "arguments": {"profile": user(), "exercise_name": "平板支撑"},
                    },
                    ensure_ascii=False,
                )
            ),
            SimpleNamespace(
                content=json.dumps(
                    {
                        "recommendations": [
                            {
                                "name": "平板支撑",
                                "score": 92,
                                "reason": "优先调用动作工具后生成",
                                "risk_warning": "",
                            },
                            {
                                "name": "深蹲",
                                "score": 88,
                                "reason": "结合动作工具结果",
                                "risk_warning": "",
                            },
                        ]
                    },
                    ensure_ascii=False,
                )
            ),
        ]
    )

    client = LLMClient(
        environ={"LLM_PROVIDER": "deepseek", "DEEPSEEK_API_KEY": "test-key"},
        chat_model=model,
        tools=[recommend_exercises, recommend_venues],
    )
    result = json.loads(client.invoke("帮我做个腿部训练推荐"))
    assert [item["name"] for item in result["recommendations"]] == ["平板支撑", "深蹲"]
    assert tool_calls == [
        ("recommend_exercises", "beginner", 2),
        ("recommend_venues", "平板支撑"),
    ]
    assert len(model.bound_tools) == 2


def test_top_level_recommend_agent_can_use_tools(monkeypatch):
    class FakeGraph:
        def __init__(self):
            self.exercises = [
                {
                    "name": "平板支撑",
                    "category": "核心训练",
                    "difficulty": 1,
                    "target": "核心稳定",
                    "equipment": "瑜伽垫",
                    "standard_json": "{}",
                }
            ]
            self.venues = [{"name": "校内健身房", "match_score": 90}]

        def refresh(self):
            return None

        def recommend_exercises(self, profile):
            return list(self.exercises)

        def recommend_venues(self, profile, exercise_name=None):
            return list(self.venues)

    model = ToolLoopModel(
        [
            SimpleNamespace(
                content=json.dumps(
                    {
                        "tool_call": "recommend_exercises",
                        "arguments": {"profile": user(), "top_k": 1},
                    },
                    ensure_ascii=False,
                )
            ),
            SimpleNamespace(
                content=json.dumps(
                    {
                        "tool_call": "recommend_venues",
                        "arguments": {"profile": user(), "exercise_name": "平板支撑"},
                    },
                    ensure_ascii=False,
                )
            ),
            SimpleNamespace(
                content=json.dumps(
                    {
                        "recommendations": [
                            {
                                "name": "平板支撑",
                                "score": 94,
                                "reason": "工具返回了匹配的核心动作",
                                "risk_warning": "",
                            }
                        ]
                    },
                    ensure_ascii=False,
                )
            ),
        ]
    )

    agent = agents.RecommendAgent(
        llm_client=LLMClient(
            environ={"LLM_PROVIDER": "deepseek", "DEEPSEEK_API_KEY": "test-key"}
        ),
        vector_store=ExerciseVectorStore(),
    )
    monkeypatch.setattr(agent, "graph", FakeGraph())
    agent.llm_client = LLMClient(
        environ={"LLM_PROVIDER": "deepseek", "DEEPSEEK_API_KEY": "test-key"},
        chat_model=model,
        tools=agent.tools(),
    )
    result = agent.recommend_with_tools(user(), exercise_name="平板支撑")
    assert result["recommendations"][0]["name"] == "平板支撑"
    assert result["tools_used"] == {"recommend_exercises": 1, "recommend_venues": 1}
    assert result["venues"][0]["name"] == "校内健身房"
    assert len(model.bound_tools) == 2


def test_mock_llm_async_calls_for_all_agents():
    profile_llm = FakeLLM(
        {
            "profile": {
                "fitness_level": "beginner",
                "goals": [],
                "preferences": [],
                "risk_flags": [],
                "habits": [],
                "summary": "结构化画像",
            }
        }
    )
    result = asyncio.run(ProfileAgent(llm_client=profile_llm).asummarize(user()))
    assert result["mode"] == "online"
    assert profile_llm.async_calls == 1


def test_evaluate_async_uses_mock_llm():
    fake = FakeLLM(
        {
            "evaluation": {
                "score": 82,
                "mistakes": [],
                "suggestions": ["保持节奏"],
                "risk_level": "low",
            }
        }
    )
    result = asyncio.run(
        EvaluateAgent(llm_client=fake).aevaluate(
            "平板支撑", 80, {"stability_score": 85}
        )
    )
    assert result["mode"] == "online"
    assert fake.async_calls == 1


def test_remaining_agents_support_mocked_async_calls():
    recommend_llm = FakeLLM(
        {
            "recommendations": [
                {
                    "name": "平板支撑",
                    "score": 90,
                    "reason": "匹配核心目标",
                    "risk_warning": "",
                }
            ]
        }
    )
    recommend = asyncio.run(
        RecommendAgent(
            llm_client=recommend_llm,
            vector_store=ExerciseVectorStore(),
        ).arecommend(user(), knowledge_base())
    )
    assert recommend["mode"] == "online"

    motivation_llm = FakeLLM(
        {
            "message": "小林，本次训练完成稳定。",
            "story": "训练地图新增一枚路标。",
            "strategy": "保持动作质量。",
            "next_goal": "下次提高2分。",
        }
    )
    motivation = asyncio.run(
        MotivationAgent(llm_client=motivation_llm).asettle(user(), 80, 20)
    )
    assert motivation["mode"] == "online"

    report_llm = FakeLLM(
        {
            "report_type": "weekly",
            "empty": False,
            "training_count": 2,
            "average_score": 80,
            "total_duration": 45,
            "strengths": ["平板支撑"],
            "weaknesses": ["深蹲"],
            "trend_analysis": "记录显示表现稳定。",
            "risk_reminders": [],
            "next_plan": ["下周训练两次"],
            "summary": "本周完成两次训练。",
        }
    )
    report = asyncio.run(
        ReportAgent(llm_client=report_llm).abuild_report(history(), "weekly")
    )
    assert report["mode"] == "online"
    assert recommend_llm.async_calls == motivation_llm.async_calls == report_llm.async_calls == 1


def test_api_key_is_not_in_exception_or_logs(caplog):
    secret = "super-secret-api-key"

    class BrokenModel:
        def invoke(self, messages):
            raise RuntimeError(f"transport failed with token {secret}")

    client = LLMClient(
        environ={
            "LLM_PROVIDER": "deepseek",
            "DEEPSEEK_API_KEY": secret,
        },
        chat_model=BrokenModel(),
    )
    with pytest.raises(LLMInvocationError) as exc_info:
        client.invoke("hello")
    assert secret not in str(exc_info.value)
    assert secret not in repr(client.config)
    assert secret not in caplog.text


def test_graph_service_use_llm_routes_through_tool_agent(monkeypatch):
    calls = []

    class FakeToolAgent:
        def recommend_with_tools(self, user, exercise_name=None, history=None, question=None):
            calls.append((user["id"], exercise_name))
            return {
                "exercises": [
                    {
                        "name": "骞虫澘鏀拺",
                        "category": "鏍稿績璁粌",
                        "difficulty": 1,
                        "target": "鏍稿績绋冲畾",
                        "equipment": "鏃犲櫒鏉?",
                        "score": 96,
                        "reason": "tool",
                        "risk_warning": "",
                    }
                ],
                "venues": [
                    {
                        "name": "鏍″唴鍋ヨ韩鎴?",
                        "location": "鏍″唴",
                        "match_score": 88,
                    }
                ],
            }

    monkeypatch.setattr("agents.RecommendAgent", FakeToolAgent)
    from app.services.graph_service import GraphService

    result = GraphService().recommend({"id": 7}, exercise_name="骞虫澘鏀拺", use_llm=True)
    assert calls == [(7, "骞虫澘鏀拺")]
    assert result.exercises[0].name == "骞虫澘鏀拺"
    assert result.venues[0].name == "鏍″唴鍋ヨ韩鎴?"
