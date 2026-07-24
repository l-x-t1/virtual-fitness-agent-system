"""
pytest 测试 — 核心接口示例（同步版，无需额外插件）

运行方式:
  pytest tests/test_api.py -v
  pytest tests/ -v
"""

import pytest
from fastapi.testclient import TestClient

from agents import AgentCoordinator
from app.main import app
from app.services import fitness_service

# 初始化 coordinator（TestClient 不触发 lifespan，需手动设置）
app.state.coordinator = AgentCoordinator()
fitness_service.coordinator = app.state.coordinator

client = TestClient(app)


def _login(username="demo", password="123456"):
    resp = client.post("/api/login", json={"username": username, "password": password})
    return resp.json()["data"]["access_token"]


def _auth_headers(username="demo", password="123456"):
    return {"Authorization": f"Bearer {_login(username, password)}"}


# ============================================================
# 认证接口
# ============================================================

class TestAuth:
    def test_login_success(self):
        resp = client.post("/api/login", json={"username": "demo", "password": "123456"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == "OK"
        assert "access_token" in body["data"]
        assert body["data"]["token_type"] == "bearer"

    def test_login_wrong_password(self):
        resp = client.post("/api/login", json={"username": "demo", "password": "wrong"})
        assert resp.status_code == 401

    def test_register_duplicate(self):
        resp = client.post("/api/register", json={
            "username": "demo", "password": "123456", "nickname": "dup",
        })
        assert resp.status_code in (400, 409)


# ============================================================
# 需要认证的接口
# ============================================================

class TestDashboard:
    def test_dashboard_authenticated(self):
        resp = client.get("/api/dashboard", headers=_auth_headers())
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "profile_summary" in data
        assert "recommendations" in data
        assert "report" in data

    def test_dashboard_no_auth(self):
        resp = client.get("/api/dashboard")
        assert resp.status_code == 401


class TestProfile:
    def test_update_profile(self):
        resp = client.post("/api/profile", json={
            "age": 25, "fitness_level": "intermediate",
            "injuries": "", "preference": "力量训练", "location": "校园西区",
        }, headers=_auth_headers())
        assert resp.status_code == 200


class TestTraining:
    def test_submit_session(self):
        resp = client.post("/api/session", json={
            "exercise_name": "深蹲", "score": 85, "duration": 30,
        }, headers=_auth_headers())
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "score" in data or "feedback" in data or "game" in data


# ============================================================
# 公开接口（无需认证）
# ============================================================

class TestPublicEndpoints:
    def test_exercises(self):
        resp = client.get("/api/exercises")
        assert resp.status_code == 200
        assert len(resp.json()["data"]["exercises"]) > 0

    def test_venues(self):
        resp = client.get("/api/venues")
        assert resp.status_code == 200
        assert "venues" in resp.json()["data"]

    def test_openapi_schema(self):
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        assert schema["info"]["title"] == "虚拟游戏化全民健身智能辅助系统 API"
        assert "login" in str(schema["paths"])


# ============================================================
# 图谱接口
# ============================================================

class TestGraph:
    def test_graph_status(self):
        resp = client.get("/api/graph/status", headers=_auth_headers())
        assert resp.status_code == 200

    def test_graph_recommend(self):
        resp = client.post("/api/graph/recommend", json={"user_id": 1}, headers=_auth_headers())
        assert resp.status_code == 200
        assert "exercises" in resp.json()["data"]


# ============================================================
# 管理端 FeatureFlag 接口
# ============================================================

class TestFeatureFlags:
    def test_list_features(self):
        resp = client.get("/api/admin/features", headers=_auth_headers("admin", "admin123"))
        assert resp.status_code == 200
        assert "features" in resp.json()["data"]

    def test_set_and_check_feature(self):
        h = _auth_headers("admin", "admin123")
        # 设置百分比
        resp = client.post("/api/admin/features/graph_search?percentage=30", headers=h)
        assert resp.status_code == 200
        # 检查 user_id=5 是否放量
        resp2 = client.get("/api/admin/features/graph_search?user_id=5", headers=h)
        assert resp2.json()["data"]["enabled"] is True
        # 检查 user_id=50 是否放量
        resp3 = client.get("/api/admin/features/graph_search?user_id=50", headers=h)
        assert resp3.json()["data"]["enabled"] is False
