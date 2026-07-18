import json
import logging

from app.agents import BaseAgent
from app.agents.embedding_store import ExerciseVectorStore
from app.agents.mediapipe_adapter import MediaPipeAdapter
from app.agents.schemas import EvaluateOutput, MotivationOutput, ProfileOutput, RecommendOutput, ReportOutput
from app.cache import cache_get_or_set
from app.cache import cache_keys
from app.repositories import FitnessRepository, session_scope
from app.llm.client import LLMConfigurationError
from knowledge_graph import FitnessKnowledgeGraph

logger = logging.getLogger(__name__)


class ProfileAgent(BaseAgent):
    prompt_module = "app.agents.prompts.profile_prompt"
    output_schema = ProfileOutput

    def summarize(self, user):
        try:
            result = self.run({"user_info": user, "history": [], "behavior": []})
            profile = result["profile"]
            return (
                f"{user.get('nickname', '用户')}，{user.get('age', 20)} 岁。"
                f"体能水平：{profile.get('fitness_level') or user.get('fitness_level', '未评估')}；"
                f"运动偏好：{profile.get('preference') or user.get('preference', '综合训练')}；"
                f"训练目标：{profile.get('goal') or '逐步提升运动表现'}；"
                f"风险提示：{profile.get('risk') or '低风险'}。"
            )
        except (LLMConfigurationError, ValueError, RuntimeError) as exc:
            logger.info("ProfileAgent LLM path skipped: %s", exc)
            return self._fallback_summary(user)

    def _fallback_summary(self, user):
        injury_text = user.get("injuries") or "暂无"
        level_map = {"beginner": "新手", "intermediate": "进阶", "advanced": "熟练"}
        level = level_map.get(user.get("fitness_level"), user.get("fitness_level") or "未评估")
        return (
            f"{user.get('nickname', '用户')}，{user.get('age', 20)} 岁，"
            f"体能水平为{level}。运动偏好：{user.get('preference') or '综合训练'}；"
            f"伤病史：{injury_text}。"
        )


class MotionAgent(BaseAgent):
    prompt_module = "app.agents.prompts.evaluate_prompt"
    output_schema = EvaluateOutput

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pose_adapter = MediaPipeAdapter()

    def evaluate(self, exercise_name, raw_score, pose_data=None):
        score = max(0, min(100, int(raw_score)))
        motion_features = self.pose_adapter.to_features(pose_data, fallback_score=score)
        try:
            result = self.run({
                "exercise_name": exercise_name,
                "raw_score": score,
                "motion_features": motion_features,
            })
            evaluation = result["evaluation"]
            llm_score = self._safe_score(evaluation.get("score"), score)
            feedback = self._format_feedback(evaluation)
            return llm_score, feedback
        except (LLMConfigurationError, ValueError, RuntimeError) as exc:
            logger.info("MotionAgent LLM path skipped: %s", exc)
            return self._fallback_evaluate(exercise_name, score)

    def pose_features(self, pose_data, fallback_score=0):
        return self.pose_adapter.to_features(pose_data, fallback_score=fallback_score)

    def _fallback_evaluate(self, exercise_name, score):
        score = max(0, min(100, int(score)))
        if score >= 90:
            feedback = "动作标准度优秀，可以适当增加节奏或组数。"
        elif score >= 75:
            feedback = "动作基本达标，继续保持核心稳定和呼吸节奏。"
        elif score >= 60:
            feedback = "动作存在偏差，建议降低速度重试。"
        else:
            feedback = "动作风险较高，请暂停进阶挑战，优先进行分解练习。"
        if exercise_name in {"深蹲", "弓步蹲", "节奏冲刺"} and score < 80:
            feedback += " 重点检查膝盖方向、髋部下沉幅度与躯干稳定。"
        if exercise_name == "平板支撑" and score < 80:
            feedback += " 注意肩、髋、踝保持一条直线。"
        if exercise_name == "开合跳" and score < 80:
            feedback += " 落地时保持轻缓，膝盖与脚尖方向一致。"
        return score, feedback

    def _format_feedback(self, evaluation):
        mistakes = [item for item in evaluation.get("mistakes", []) if item]
        suggestions = [item for item in evaluation.get("suggestions", []) if item]
        parts = []
        if mistakes:
            parts.append("主要问题：" + "；".join(mistakes))
        if suggestions:
            parts.append("建议：" + "；".join(suggestions))
        return "。".join(parts) or "动作表现稳定，继续保持当前训练节奏。"

    def _safe_score(self, value, default):
        try:
            return int(round(max(0, min(100, float(value)))))
        except (TypeError, ValueError):
            return default


class RecommendAgent(BaseAgent):
    prompt_module = "app.agents.prompts.recommend_prompt"
    output_schema = RecommendOutput

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            from app.graph.neo4j_fitness_graph import Neo4jFitnessGraph
            self.graph = Neo4jFitnessGraph()
            logger.info("RecommendAgent using Neo4j graph")
        except Exception:
            self.graph = FitnessKnowledgeGraph()
            logger.info("RecommendAgent using lightweight graph (Neo4j unavailable)")
        self.vector_store = ExerciseVectorStore()

    def recommend(self, user, exercise_name=None):
        self.graph.refresh()
        graph_exercises = self.graph.recommend_exercises(user)
        exercises = self._rag_candidates(user, graph_exercises, exercise_name)
        venues = self.graph.recommend_venues(user, exercise_name)
        try:
            result = self.run({
                "profile": user,
                "history": [],
                "current_exercise": exercise_name,
                "retrieval_context": [item.get("rag_context") for item in exercises if item.get("rag_context")],
                "candidates": [
                    {
                        "name": item.get("name"),
                        "category": item.get("category"),
                        "difficulty": item.get("difficulty"),
                        "target": item.get("target"),
                        "equipment": item.get("equipment"),
                        "reason": item.get("reason"),
                        "score": item.get("match_score"),
                    }
                    for item in exercises
                ],
            })
            exercises = self._merge_llm_recommendations(exercises, result.get("recommendations", []))
        except (LLMConfigurationError, ValueError, RuntimeError) as exc:
            logger.info("RecommendAgent LLM path skipped: %s", exc)
        return {"exercises": exercises, "venues": venues}

    def _rag_candidates(self, user, graph_exercises, exercise_name):
        try:
            vector_exercises = self.vector_store.search(user, self.graph.exercises, exercise_name, top_k=5)
        except RuntimeError as exc:
            logger.info("RecommendAgent FAISS path skipped: %s", exc)
            return graph_exercises

        if not vector_exercises:
            return graph_exercises

        merged = []
        used = set()
        graph_by_name = {item.get("name"): item for item in graph_exercises}
        for item in vector_exercises:
            name = item.get("name")
            if not name:
                continue
            base = graph_by_name.get(name, item)
            merged.append({
                **base,
                "rag_score": item.get("rag_score"),
                "rag_context": item.get("rag_context"),
                "match_score": max(float(base.get("match_score") or 0), float(item.get("rag_score") or 0)),
            })
            used.add(name)
        merged.extend(item for item in graph_exercises if item.get("name") not in used)
        return merged[:5]

    def _merge_llm_recommendations(self, exercises, recommendations):
        by_name = {item.get("name"): item for item in exercises}
        ranked = []
        used = set()
        for recommendation in recommendations:
            name = recommendation.get("name")
            if name not in by_name:
                continue
            score = recommendation.get("score")
            item = {
                **by_name[name],
                "reason": recommendation.get("reason") or by_name[name].get("reason"),
                "match_score": self._safe_score(score, by_name[name].get("match_score")),
            }
            ranked.append(item)
            used.add(name)
        ranked.extend(item for item in exercises if item.get("name") not in used)
        return ranked[:5]

    def _safe_score(self, value, default):
        try:
            return round(max(0, min(100, float(value))), 1)
        except (TypeError, ValueError):
            return default

    def today_plan(self, user, report):
        rec = self.recommend(user)
        exercises = rec["exercises"][:3]
        average = report.get("average", 0)
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


class GameAgent(BaseAgent):
    prompt_module = "app.agents.prompts.motivation_prompt"
    output_schema = MotivationOutput

    def settle(self, repo: FitnessRepository, user, score, duration):
        result = repo.settle_points(user["id"], score, duration)
        try:
            motivation = self.run({
                "progress": {
                    "score": score,
                    "duration": duration,
                    "points": result.get("points"),
                    "total_points": result.get("total_points"),
                    "level": result.get("level"),
                },
                "emotion": "training_completed",
                "achievement": result.get("unlocked", []),
            })
            return {**result, **motivation}
        except (LLMConfigurationError, ValueError, RuntimeError) as exc:
            logger.info("GameAgent LLM path skipped: %s", exc)
            return {
                **result,
                "message": self._fallback_message(user, score),
                "strategy": "保持稳定训练节奏，优先保证动作质量。",
                "next_goal": "下一次训练争取在标准动作前提下提升 3 分。",
            }

    def _fallback_message(self, user, score):
        nickname = user.get("nickname", "用户")
        if score >= 90:
            return f"{nickname}，本次动作质量很稳，可以尝试增加一组训练。"
        if score >= 75:
            return f"{nickname}，本次训练已经达标，继续保持节奏。"
        return f"{nickname}，先把动作做稳，降低速度会更容易进步。"


class ReportAgent(BaseAgent):
    prompt_module = "app.agents.prompts.report_prompt"
    output_schema = ReportOutput

    def build_report(self, user_id):
        with session_scope() as session:
            sessions = FitnessRepository(session).recent_sessions(user_id, 10)
        if not sessions:
            return {"average": 0, "count": 0, "summary": "暂无训练记录。", "sessions": []}

        average = round(sum(item["score"] for item in sessions) / len(sessions), 1)
        weak = min(sessions, key=lambda x: x["score"])
        best = max(sessions, key=lambda x: x["score"])
        trend = list(reversed([
            {
                "exercise_name": item["exercise_name"],
                "score": item["score"],
                "points": item["points"],
                "duration": item["duration"],
                "created_at": str(item["created_at"]),
            }
            for item in sessions[:7]
        ]))
        report = {
            "average": average,
            "count": len(sessions),
            "weak_exercise": weak["exercise_name"],
            "best_exercise": best["exercise_name"],
            "summary": f"近 {len(sessions)} 次训练平均分 {average}，薄弱动作是 {weak['exercise_name']}。",
            "suggestion": f"保持 {best['exercise_name']} 的训练优势；{weak['exercise_name']} 建议降低速度。",
            "trend": trend,
            "sessions": sessions,
        }
        try:
            generated = self.run({
                "profile": {"user_id": user_id},
                "recommendation": {},
                "evaluation": {
                    "average": average,
                    "weak_exercise": weak["exercise_name"],
                    "best_exercise": best["exercise_name"],
                },
                "history": sessions,
            })
            plan = generated.get("plan") or []
            return {
                **report,
                "title": generated.get("title") or "训练报告",
                "summary": generated.get("summary") or report["summary"],
                "analysis": generated.get("analysis") or "",
                "plan": plan,
                "suggestion": "；".join(plan) or report["suggestion"],
            }
        except (LLMConfigurationError, ValueError, RuntimeError) as exc:
            logger.info("ReportAgent LLM path skipped: %s", exc)
            return report


class AgentCoordinator:
    def __init__(self):
        self.profile = ProfileAgent()
        self.motion = MotionAgent()
        self.recommendation = RecommendAgent()
        self.game = GameAgent()
        self.report = ReportAgent()

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
        return {"score": score, "feedback": feedback, "game": game, "recommendations": self.recommendation.recommend(updated_user, exercise_name)}

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
