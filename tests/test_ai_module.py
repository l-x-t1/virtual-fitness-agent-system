from app.ai.coach import AICoach
from app.ai.knowledge_base import FitnessKnowledgeBase
from app.ai.llm import AIProviderError, UnifiedLLM
from app.ai.memory import ConversationStore
from app.main import app


class OfflineLLM(UnifiedLLM):
    def chat(self, *args, **kwargs):
        raise AIProviderError("offline")

    def available(self):
        return [
            {"provider": "deepseek", "default_model": "deepseek-v4-flash", "configured": False},
            {"provider": "dashscope", "default_model": "qwen-plus", "configured": False},
        ]


class OnlineLLM(OfflineLLM):
    def chat(self, *args, **kwargs):
        return "这是在线模型的动态回答"


def user():
    return {
        "id": 7,
        "nickname": "测试用户",
        "fitness_level": "beginner",
        "injuries": "膝盖偶尔不适",
        "preference": "低冲击训练",
    }


def test_ai_routes_are_registered():
    paths = app.openapi()["paths"]
    assert "/api/ai/chat" in paths
    assert "/api/ai/sessions" in paths
    assert "/api/ai/plans" in paths
    assert "/api/ai/profile" in paths
    assert "/api/ai/corrections" in paths
    assert "/api/ai/knowledge" in paths
    assert "/api/ai/knowledge/import" in paths
    assert "/api/ai/providers/test" in paths


def test_conversations_are_isolated_by_user():
    store = ConversationStore(db_path=":memory:")
    session = store.create(1)
    assert store.get(session.id, 1).id == session.id
    assert store.get(session.id, 2) is None
    assert store.delete(session.id, 2) is False


def test_conversations_survive_store_restart(tmp_path):
    path = tmp_path / "sessions.db"
    first = ConversationStore(db_path=path)
    session = first.create(1, "持久化测试")
    first.add(session, "user", "测试消息")
    session.state["turn_count"] = 1
    first.save(session)
    first.close()

    second = ConversationStore(db_path=path)
    restored = second.get(session.id, 1)
    assert restored.messages == [{"role": "user", "content": "测试消息"}]
    assert restored.state["turn_count"] == 1


def test_local_knowledge_base_retrieves_squat_guidance(tmp_path):
    hits = FitnessKnowledgeBase(custom_source=tmp_path / "custom.json").search("深蹲膝盖方向", top_k=2)
    assert hits
    assert any(item["id"] == "squat" for item in hits)


def test_demo_chat_keeps_context_and_returns_sources():
    coach = AICoach(llm=OfflineLLM(), memory=ConversationStore(db_path=":memory:"))
    session = coach.create_session(user()["id"], "新对话 10:30")
    result = coach.chat(
        user(),
        [],
        {"session_id": session["id"], "message": "深蹲要注意什么？", "provider": "deepseek", "model": None},
    )
    assert result["mode"] == "demo"
    assert result["sources"]
    assert coach.sessions(user()["id"])[0]["message_count"] == 2
    detail = coach.session(user()["id"], session["id"])
    assert detail["messages"][0]["role"] == "user"
    assert detail["title"] == "深蹲要注意什么？"


def test_long_term_memory_survives_across_sessions_and_users():
    clean_user = {
        "id": 99,
        "nickname": "记忆测试用户",
        "fitness_level": "beginner",
        "injuries": "",
        "preference": "综合训练",
    }
    coach = AICoach(llm=OfflineLLM(), memory=ConversationStore(db_path=":memory:"))
    first = coach.create_session(clean_user["id"], "first")
    coach.chat(
        clean_user,
        [],
        {"session_id": first["id"], "message": "我膝盖不好", "provider": "deepseek", "model": None},
    )

    second = coach.create_session(clean_user["id"], "next-month")
    result = coach.chat(
        clean_user,
        [],
        {"session_id": second["id"], "message": "帮我制定训练计划", "provider": "deepseek", "model": None},
    )

    assert result["memory"]["long_term_hits"] >= 1
    assert "膝盖" in result["answer"]
    assert coach.memory.search_long_term(100, "帮我制定训练计划") == []


def test_demo_plan_is_structured_and_risk_aware():
    coach = AICoach(llm=OfflineLLM(), memory=ConversationStore(db_path=":memory:"))
    result = coach.plan(user(), [], {"duration_minutes": 25, "goal": "提升体能"})
    assert result["mode"] == "demo"
    assert result["plan"]["duration_minutes"] == 25
    assert result["plan"]["exercises"][0]["name"] == "椅子辅助深蹲"


def test_demo_answers_are_intent_specific():
    coach = AICoach(llm=OfflineLLM(), memory=ConversationStore(db_path=":memory:"))
    profile = coach.profile(user(), [], use_llm=False)
    frequency = coach._demo_answer("新手每周训练几次？", [], profile)
    fat_loss = coach._demo_answer("体脂率怎么降？", [], profile)
    assert "每周2到3次" in frequency
    assert "能量缺口" in fat_loss
    assert frequency != fat_loss


def test_profile_contains_training_metrics():
    coach = AICoach(llm=OfflineLLM(), memory=ConversationStore(db_path=":memory:"))
    history = [
        {"exercise_name": "深蹲", "score": 90, "duration": 1200, "created_at": "2026-07-20T10:00:00"},
        {"exercise_name": "平板支撑", "score": 70, "duration": 600, "created_at": "2026-07-17T10:00:00"},
    ]
    profile = coach.profile(user(), history, use_llm=False)
    assert profile["metrics"]["average_score"] == 80
    assert profile["metrics"]["total_minutes"] == 30
    assert profile["metrics"]["best_exercise"] == "深蹲"


def test_custom_knowledge_import_rebuilds_index(tmp_path):
    base = tmp_path / "base.json"
    custom = tmp_path / "custom.json"
    base.write_text(json.dumps([{"id": "base", "title": "基础", "content": "基础训练资料"}]), encoding="utf-8")
    knowledge = FitnessKnowledgeBase(source=base, custom_source=custom)
    result = knowledge.import_documents([
        {"title": "弹力带划船", "content": "保持肩胛稳定，肘部向后拉。", "category": "动作指导"}
    ])
    assert result["imported"] == 1
    assert knowledge.stats()["total"] == 2


def test_unified_llm_openai_compatible_request(monkeypatch):
    monkeypatch.setenv("AI_DEEPSEEK_API_KEY", "test-key")
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "模型回答"}}]}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["headers"] = kwargs["headers"]
        captured["payload"] = kwargs["json"]
        return Response()

    monkeypatch.setattr(httpx, "post", fake_post)
    answer = UnifiedLLM().chat([{"role": "user", "content": "你好"}], "deepseek", "deepseek-chat")
    assert answer == "模型回答"
    assert captured["url"] == "https://api.deepseek.com/chat/completions"
    assert captured["payload"]["model"] == "deepseek-chat"
    assert captured["headers"]["Authorization"] == "Bearer test-key"


def test_provider_connection_reports_missing_key():
    coach = AICoach(llm=OfflineLLM(), memory=ConversationStore(db_path=":memory:"))
    result = coach.test_provider("deepseek")
    assert result["ok"] is False
    assert result["provider"] == "deepseek"
import json

import httpx
