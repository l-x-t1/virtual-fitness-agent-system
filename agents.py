"""Legacy-compatible adapters for the structured agents in :mod:`app.agents`.

Database and graph access stay in this compatibility layer.  The reusable agent
implementations under ``app/agents`` only operate on caller-provided data.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from app.agents.prompts.tool_recommend_prompt import PROMPT_TEMPLATE as TOOL_RECOMMEND_PROMPT
from app.agents import (
    EvaluateAgent as StructuredEvaluateAgent,
    MotivationAgent as StructuredMotivationAgent,
    ProfileAgent as StructuredProfileAgent,
    RecommendAgent as StructuredRecommendAgent,
    ReportAgent as StructuredReportAgent,
)
from app.cache import cache_get_or_set
from app.cache import cache_keys
from app.repositories import FitnessRepository, session_scope
from knowledge_graph import FitnessKnowledgeGraph

logger = logging.getLogger(__name__)


class ProfileAgent(StructuredProfileAgent):
    """Keep the dashboard's historical string summary API."""

    def summarize_structured(
        self,
        user: dict[str, Any],
        history: list[dict[str, Any]] | None = None,
        behavior: list[Any] | None = None,
    ) -> dict[str, Any]:
        return super().summarize(user, history=history, behavior=behavior)

    def summarize(self, user):
        result = self.summarize_structured(user)
        profile = result["profile"]
        summary = (
            f"{user.get('nickname', '用户')}，{user.get('age', 20)} 岁。"
            f"体能水平：{profile['fitness_level']}；"
            f"运动偏好：{'、'.join(profile['preferences']) or '信息不足'}；"
            f"训练目标：{'、'.join(profile['goals']) or '信息不足'}；"
            f"风险提示：{'、'.join(profile['risk_flags']) or '未发现输入中的明确风险'}。"
        )
        if result["mode"] == "fallback":
            summary += "（fallback：未调用在线模型）"
        return summary


class MotionAgent(StructuredEvaluateAgent):
    """Preserve ``(score, feedback)`` while exposing structured evaluation."""

    def evaluate_structured(self, exercise_name, raw_score, pose_data=None):
        return super().evaluate(exercise_name, raw_score, pose_data)

    def evaluate(self, exercise_name, raw_score, pose_data=None):
        result = self.evaluate_structured(exercise_name, raw_score, pose_data)
        evaluation = result["evaluation"]
        mistakes = [item for item in evaluation["mistakes"] if item]
        suggestions = [item for item in evaluation["suggestions"] if item]
        parts = []
        if mistakes:
            parts.append("主要问题：" + "；".join(mistakes))
        if suggestions:
            parts.append("建议：" + "；".join(suggestions))
        feedback = "。".join(parts) or "当前可用特征未发现明确动作问题。"
        if result["mode"] == "fallback":
            feedback = "fallback（未调用在线模型）：" + feedback
        return int(round(evaluation["score"])), feedback


class RecommendAgent(StructuredRecommendAgent):
    """Add the existing graph/venue integration around the pure recommendation agent."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._tool_context: dict[str, list[dict[str, Any]]] = {}
        try:
            from app.graph.neo4j_fitness_graph import Neo4jFitnessGraph

            self.graph = Neo4jFitnessGraph()
            logger.info("RecommendAgent using Neo4j graph")
        except Exception:
            self.graph = FitnessKnowledgeGraph()
            logger.info("RecommendAgent using lightweight graph (Neo4j unavailable)")

    def tools(self) -> list[Any]:
        return [
            {
                "name": "recommend_exercises",
                "description": "从知识图谱中获取适合当前用户的动作候选。",
                "handler": self._tool_recommend_exercises,
            },
            {
                "name": "recommend_venues",
                "description": "从知识图谱中获取适合当前用户或动作的场馆候选。",
                "handler": self._tool_recommend_venues,
            },
        ]

    def _tool_recommend_exercises(
        self,
        profile: dict[str, Any] | None = None,
        user: dict[str, Any] | None = None,
        top_k: int = 5,
    ) -> dict[str, Any]:
        """Return exercise candidates from the active graph source."""
        self.graph.refresh()
        profile_data = dict(profile or user or {})
        exercises = self.graph.recommend_exercises(profile_data)[: max(1, min(int(top_k or 5), 5))]
        self._tool_context["recommend_exercises"] = exercises
        return {"exercises": exercises}

    def _tool_recommend_venues(
        self,
        profile: dict[str, Any] | None = None,
        user: dict[str, Any] | None = None,
        exercise_name: str | None = None,
    ) -> dict[str, Any]:
        """Return venue candidates for the active user and exercise."""
        self.graph.refresh()
        profile_data = dict(profile or user or {})
        venues = self.graph.recommend_venues(profile_data, exercise_name)
        self._tool_context["recommend_venues"] = venues
        return {"venues": venues}

    def recommend_with_tools(
        self,
        user: dict[str, Any],
        exercise_name: str | None = None,
        history: list[dict[str, Any]] | None = None,
        question: str | None = None,
    ) -> dict[str, Any]:
        self._tool_context = {}
        self.graph.refresh()
        payload = {
            "profile": dict(user or {}),
            "history": list(history or []),
            "current_exercise": exercise_name,
            "question": question or "请结合工具结果给出训练动作推荐。",
        }
        prompt = TOOL_RECOMMEND_PROMPT.format(
            input_json=json.dumps(payload, ensure_ascii=False, default=str)
        )
        raw = self._bound_client(self.tools()).invoke(prompt)
        structured = self._parse(raw)
        exercises = self._tool_context.get("recommend_exercises") or list(self.graph.exercises)
        venues = self._tool_context.get("recommend_venues") or list(self.graph.venues)
        recommendations = self._whitelist(structured["recommendations"], exercises)
        if not recommendations:
            return self._fallback_from_tools(user, exercises, venues, "model_returned_no_valid_candidates")
        graph_by_name = {item.get("name"): item for item in exercises}
        merged_exercises = []
        for recommendation in recommendations:
            base = graph_by_name.get(recommendation["name"], {})
            merged_exercises.append(
                {
                    **base,
                    "name": recommendation["name"],
                    "match_score": recommendation["score"],
                    "reason": recommendation["reason"],
                    "risk_warning": recommendation["risk_warning"],
                }
            )
        return {
            "exercises": merged_exercises,
            "venues": venues,
            "recommendations": recommendations,
            "mode": "online",
            "retrieval_backend": "tool-call",
            "tools_used": {
                "recommend_exercises": len(self._tool_context.get("recommend_exercises", [])),
                "recommend_venues": len(self._tool_context.get("recommend_venues", [])),
            },
            **{key: value for key, value in structured.items() if key != "recommendations"},
        }

    def _fallback_from_tools(
        self,
        user: dict[str, Any],
        exercises: list[dict[str, Any]],
        venues: list[dict[str, Any]],
        reason: str,
    ) -> dict[str, Any]:
        fallback = self._fallback_result(user, exercises, reason)
        graph_by_name = {item.get("name"): item for item in exercises}
        merged_exercises = []
        for recommendation in fallback["recommendations"]:
            base = graph_by_name.get(recommendation["name"], {})
            merged_exercises.append(
                {
                    **base,
                    "name": recommendation["name"],
                    "match_score": recommendation["score"],
                    "reason": recommendation["reason"],
                    "risk_warning": recommendation["risk_warning"],
                }
            )
        return {
            "exercises": merged_exercises,
            "venues": venues,
            **fallback,
            "retrieval_backend": "tool-call",
        }

    def recommend_structured(
        self,
        user: dict[str, Any],
        exercise_name: str | None = None,
        history: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        self.graph.refresh()
        return super().recommend(
            user,
            knowledge_base=list(self.graph.exercises),
            history=history or [],
            current_exercise=exercise_name,
            top_k=5,
        )

    def recommend(self, user, exercise_name=None):
        self.graph.refresh()
        graph_exercises = self.graph.recommend_exercises(user)
        structured = StructuredRecommendAgent.recommend(
            self,
            user,
            knowledge_base=list(self.graph.exercises),
            history=[],
            current_exercise=exercise_name,
            top_k=5,
        )
        venues = self.graph.recommend_venues(user, exercise_name)
        graph_by_name = {item.get("name"): item for item in self.graph.exercises}
        graph_by_name.update({item.get("name"): item for item in graph_exercises})
        exercises = []
        for recommendation in structured["recommendations"]:
            base = graph_by_name.get(recommendation["name"], {})
            exercises.append(
                {
                    **base,
                    "name": recommendation["name"],
                    "match_score": recommendation["score"],
                    "reason": recommendation["reason"],
                    "risk_warning": recommendation["risk_warning"],
                }
            )
        return {
            "exercises": exercises,
            "venues": venues,
            **{key: value for key, value in structured.items() if key != "recommendations"},
        }

    async def arecommend(
        self,
        user: dict[str, Any],
        exercise_name: str | None = None,
        history: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        self.graph.refresh()
        return await StructuredRecommendAgent.arecommend(
            self,
            user,
            knowledge_base=list(self.graph.exercises),
            history=history or [],
            current_exercise=exercise_name,
            top_k=5,
        )

    def today_plan(self, user, report):
        rec = self.recommend(user)
        exercises = rec["exercises"][:3]
        average = report.get("average", report.get("average_score", 0))
        if user.get("fitness_level") == "beginner" or average < 75:
            intensity, duration, note = "低到中等", 18, "优先保证动作标准度。"
        elif average >= 88:
            intensity, duration, note = "中高强度", 28, "近期表现稳定，可增加节奏和组数。"
        else:
            intensity, duration, note = "中等", 22, "保持当前难度。"
        return {
            "title": "今日智能训练方案",
            "duration_minutes": duration,
            "intensity": intensity,
            "steps": [item["name"] for item in exercises],
            "reason": f"依据体能水平、伤病史、近期平均分和场馆环境生成。{note}",
        }


class GameAgent(StructuredMotivationAgent):
    """Keep repository point settlement outside the reusable motivation agent."""

    def settle_structured(self, user, score, duration, settlement, history=None):
        return super().settle(
            user,
            score,
            duration,
            points=settlement.get("points", 0),
            total_points=settlement.get("total_points", 0),
            level=settlement.get("level", 1),
            history=history or [],
            unlocked_levels=settlement.get("unlocked", []),
        )

    def settle(self, repo: FitnessRepository, user, score, duration):
        settlement = repo.settle_points(user["id"], score, duration)
        return {
            **settlement,
            **self.settle_structured(user, score, duration, settlement),
        }

    async def asettle(self, repo: FitnessRepository, user, score, duration, history=None):
        settlement = repo.settle_points(user["id"], score, duration)
        motivation = await StructuredMotivationAgent.asettle(
            self,
            user,
            score,
            duration,
            points=settlement.get("points", 0),
            total_points=settlement.get("total_points", 0),
            level=settlement.get("level", 1),
            history=history or [],
            unlocked_levels=settlement.get("unlocked", []),
        )
        return {**settlement, **motivation}


class ReportAgent(StructuredReportAgent):
    """Keep the historical ``user_id`` API and repository lookup."""

    def _sessions_for(self, user_id: int) -> list[dict[str, Any]]:
        with session_scope() as session:
            return FitnessRepository(session).recent_sessions(user_id, 31)

    def build_report_structured(
        self,
        training_records: list[dict[str, Any]],
        report_type: str = "weekly",
        profile: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return super().build_report(training_records, report_type, profile)

    def build_report(
        self,
        user_id,
        report_type="weekly",
        training_records=None,
        profile=None,
    ):
        sessions = self._sessions_for(user_id) if training_records is None else list(training_records)
        period_sessions = self._period_records(sessions, self._report_type(report_type))
        structured = self.build_report_structured(
            period_sessions, report_type, profile or {"user_id": user_id}
        )
        return self._legacy_report(structured, period_sessions)

    async def abuild_report(
        self,
        user_id,
        report_type="weekly",
        training_records=None,
        profile=None,
    ):
        if training_records is None:
            sessions = await asyncio.to_thread(self._sessions_for, user_id)
        else:
            sessions = list(training_records)
        sessions = self._period_records(sessions, self._report_type(report_type))
        return await StructuredReportAgent.abuild_report(
            self, sessions, report_type, profile or {"user_id": user_id}
        )

    def _legacy_report(self, structured, sessions):
        trend = [
            {
                "exercise_name": item.get("exercise_name"),
                "score": item.get("score"),
                "points": item.get("points"),
                "duration": item.get("duration"),
                "created_at": str(item.get("created_at", "")),
            }
            for item in reversed(sessions[:7])
        ]
        return {
            **structured,
            "average": structured["average_score"],
            "count": structured["training_count"],
            "weak_exercise": (
                structured["weaknesses"][0] if structured["weaknesses"] else None
            ),
            "best_exercise": (
                structured["strengths"][0] if structured["strengths"] else None
            ),
            "suggestion": "；".join(structured["next_plan"]),
            "plan": structured["next_plan"],
            "analysis": structured["trend_analysis"],
            "trend": trend,
            "sessions": sessions,
        }


class AgentCoordinator:
    def __init__(self):
        self.profile = ProfileAgent()
        self.motion = MotionAgent()
        self.recommendation = RecommendAgent()
        self.game = GameAgent()
        self.report = ReportAgent()

    # ---- 工具绑定（复用 LLMClient.bind_tools，人员4） ----

    def recommend_tools(self) -> list[Any]:
        """推荐 Agent 暴露的工具：recommend_exercises / recommend_venues。"""
        return self.recommendation.tools()

    def bound_recommend_llm(self):
        """把推荐工具绑定到推荐 Agent 的 LLMClient（Function Calling 用）。"""
        return self.recommendation.llm_client.bind_tools(self.recommend_tools())

    def recommend_with_tools(
        self,
        user: dict[str, Any],
        exercise_name: str | None = None,
        question: str | None = None,
    ) -> dict[str, Any]:
        """通过 LLM 的 Function Calling 触发 recommend_exercises 工具完成推荐。"""
        return self.recommendation.recommend_with_tools(
            user, exercise_name=exercise_name, question=question
        )

    async def run_workflow(self, user_message: str, user_id: int | str) -> dict[str, Any]:
        """运行规划→推荐→评估→激励→报告 完整 LangGraph 链路。"""
        from app.ai.langgraph_agent import run_agent

        return await run_agent(user_message, user_id)

    def dashboard(self, user):
        return cache_get_or_set(cache_keys.dashboard(user["id"]), lambda: self._dashboard(user))

    def _dashboard(self, user):
        report = self.report.build_report(user["id"])
        rec = self.recommendation.recommend(user)
        with session_scope() as session:
            repo = FitnessRepository(session)
            return {
                "profile_summary": self.profile.summarize(user),
                "today_plan": self.recommendation.today_plan(user, report),
                "recommendations": rec,
                "report": report,
                "badges": repo.badges_for_user(user["id"]),
                "point_logs": repo.point_logs(user["id"]),
                "agent_flow": [
                    {"name": "画像智能体", "status": "已分析", "detail": "同步年龄、体能、偏好和伤病标签"},
                    {"name": "图谱推荐智能体", "status": "已推荐", "detail": "匹配用户、动作、场馆和环境关系"},
                    {"name": "动作评估智能体", "status": "待训练", "detail": "训练后生成动作评分和纠错建议"},
                ],
                "tips": repo.tips(),
                "notifications": repo.notifications(),
            }

    def submit_session(self, user_id, exercise_name, raw_score, duration):
        with session_scope() as session:
            repo = FitnessRepository(session)
            user = repo.user_by_id(user_id)
            score, feedback = self.motion.evaluate(exercise_name, raw_score)
            game = self.game.settle(repo, user, score, duration)
            repo.add_session(user_id, exercise_name, score, duration, game["points"], feedback)
            updated_user = repo.user_by_id(user_id)
        return {
            "score": score,
            "feedback": feedback,
            "game": game,
            "recommendations": self.recommendation.recommend(updated_user, exercise_name),
        }

    def exercises(self):
        return cache_get_or_set(cache_keys.EXERCISES, self._exercises)

    def _exercises(self):
        with session_scope() as session:
            rows = FitnessRepository(session).exercises()
        return [{**row, "standard": json.loads(row["standard_json"] or "{}")} for row in rows]

    def venues(self):
        return cache_get_or_set(cache_keys.VENUES, self._venues)

    def _venues(self):
        with session_scope() as session:
            return FitnessRepository(session).venues()

    def sessions(self, user_id):
        return cache_get_or_set(cache_keys.user_sessions(user_id), lambda: self._sessions(user_id))

    def _sessions(self, user_id):
        with session_scope() as session:
            return FitnessRepository(session).recent_sessions(user_id, 20)

    def badges(self, user_id):
        return cache_get_or_set(cache_keys.user_badges(user_id), lambda: self._badges(user_id))

    def _badges(self, user_id):
        with session_scope() as session:
            return FitnessRepository(session).badges_for_user(user_id)

    def point_logs(self, user_id):
        return cache_get_or_set(cache_keys.user_points(user_id), lambda: self._point_logs(user_id))

    def _point_logs(self, user_id):
        with session_scope() as session:
            return FitnessRepository(session).point_logs(user_id)

    def save_pose_record(self, body):
        features = self.motion.pose_features(body, fallback_score=body.get("stability_score", 0))
        body = dict(body)
        try:
            raw_payload = json.loads(body.get("raw_landmarks_json") or "{}")
            if not isinstance(raw_payload, dict):
                raw_payload = {"landmarks": raw_payload}
        except json.JSONDecodeError:
            raw_payload = {"raw": body.get("raw_landmarks_json")}
        raw_payload["motion_features"] = features
        body["raw_landmarks_json"] = json.dumps(raw_payload, ensure_ascii=False)
        with session_scope() as session:
            return FitnessRepository(session).add_pose_record(body)
