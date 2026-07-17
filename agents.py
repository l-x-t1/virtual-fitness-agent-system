import json

from app.cache import cache_get_or_set
from app.cache import cache_keys
from app.repositories import FitnessRepository, session_scope
from knowledge_graph import FitnessKnowledgeGraph


class ProfileAgent:
    def summarize(self, user):
        injury_text = user.get("injuries") or "暂无"
        level_map = {"beginner": "新手", "intermediate": "进阶", "advanced": "熟练"}
        level = level_map.get(user.get("fitness_level"), user.get("fitness_level"))
        return f"{user['nickname']}，{user.get('age', 20)} 岁，体能水平为{level}。运动偏好：{user.get('preference')}；伤病史：{injury_text}。"


class MotionAgent:
    def evaluate(self, exercise_name, raw_score):
        score = max(0, min(100, int(raw_score)))
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


class RecommendAgent:
    def __init__(self):
        self.graph = FitnessKnowledgeGraph()

    def recommend(self, user, exercise_name=None):
        self.graph.refresh()
        return {"exercises": self.graph.recommend_exercises(user), "venues": self.graph.recommend_venues(user, exercise_name)}

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


class GameAgent:
    def settle(self, repo: FitnessRepository, user, score, duration):
        return repo.settle_points(user["id"], score, duration)


class ReportAgent:
    def build_report(self, user_id):
        with session_scope() as session:
            sessions = FitnessRepository(session).recent_sessions(user_id, 10)
        if not sessions:
            return {"average": 0, "count": 0, "summary": "暂无训练记录。", "sessions": []}
        average = round(sum(item["score"] for item in sessions) / len(sessions), 1)
        weak = min(sessions, key=lambda x: x["score"])
        best = max(sessions, key=lambda x: x["score"])
        trend = list(reversed([
            {"exercise_name": item["exercise_name"], "score": item["score"], "points": item["points"], "duration": item["duration"], "created_at": str(item["created_at"])}
            for item in sessions[:7]
        ]))
        return {
            "average": average,
            "count": len(sessions),
            "weak_exercise": weak["exercise_name"],
            "best_exercise": best["exercise_name"],
            "summary": f"近 {len(sessions)} 次训练平均分 {average}，薄弱动作是 {weak['exercise_name']}。",
            "suggestion": f"保持 {best['exercise_name']} 的训练优势；{weak['exercise_name']} 建议降低速度。",
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
        with session_scope() as session:
            return FitnessRepository(session).add_pose_record(body)
