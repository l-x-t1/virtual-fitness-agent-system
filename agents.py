from database import execute, get_row, list_rows
from knowledge_graph import FitnessKnowledgeGraph


class ProfileAgent:
    def summarize(self, user):
        injury_text = user["injuries"] or "暂无"
        level_map = {"beginner": "新手", "intermediate": "进阶", "advanced": "熟练"}
        level = level_map.get(user["fitness_level"], user["fitness_level"])
        return (
            f"{user['nickname']}，{user['age']} 岁，体能水平为{level}。"
            f"运动偏好：{user['preference']}；伤病史：{injury_text}。"
            "画像智能体会把这些信息同步给图谱推荐智能体和游戏激励智能体。"
        )


class MotionAgent:
    def evaluate(self, exercise_name, raw_score):
        score = max(0, min(100, int(raw_score)))
        if score >= 90:
            feedback = "动作标准度优秀，可以适当增加节奏或组数。"
        elif score >= 75:
            feedback = "动作基本达标，继续保持核心稳定和呼吸节奏。"
        elif score >= 60:
            feedback = "动作存在偏差，建议观看虚拟智能体演示后降低速度重试。"
        else:
            feedback = "动作风险较高，请暂停进阶挑战，优先进行分解练习。"

        if exercise_name in {"深蹲", "弓步蹲", "节奏冲刺"} and score < 80:
            feedback += " 重点检查膝盖方向、髋部下沉幅度与躯干稳定。"
        if exercise_name == "平板支撑" and score < 80:
            feedback += " 注意肩、髋、踝保持一条直线，避免塌腰。"
        if exercise_name == "开合跳" and score < 80:
            feedback += " 落地时保持轻缓，膝盖与脚尖方向一致。"
        return score, feedback


class RecommendAgent:
    def __init__(self):
        self.graph = FitnessKnowledgeGraph()

    def recommend(self, user, exercise_name=None):
        self.graph.refresh()
        return {
            "exercises": self.graph.recommend_exercises(user),
            "venues": self.graph.recommend_venues(user, exercise_name),
        }

    def today_plan(self, user, report):
        rec = self.recommend(user)
        exercises = rec["exercises"][:3]
        average = report.get("average", 0)
        if user.get("fitness_level") == "beginner" or average < 75:
            intensity = "低到中等"
            duration = 18
            note = "优先保证动作标准度，采用低速分解训练。"
        elif average >= 88:
            intensity = "中高强度"
            duration = 28
            note = "近期表现稳定，可增加节奏和组合动作。"
        else:
            intensity = "中等"
            duration = 22
            note = "保持当前难度，重点提升连贯性和稳定性。"
        return {
            "title": "今日智能训练方案",
            "duration_minutes": duration,
            "intensity": intensity,
            "steps": [item["name"] for item in exercises],
            "reason": f"依据体能水平、伤病史、近期平均分和场馆环境生成。{note}",
        }


class GameAgent:
    def settle(self, user, score, duration):
        base = 10 + duration // 10
        bonus = 24 if score >= 92 else 16 if score >= 80 else 8 if score >= 65 else 4
        points = base + bonus
        new_total = user["points"] + points
        new_level = max(user["level"], new_total // 120 + 1)
        execute("UPDATE users SET points = ?, level = ? WHERE id = ?", (new_total, new_level, user["id"]))
        execute(
            """
            INSERT INTO point_logs(user_id, source_type, points_change, total_points, description)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user["id"], "training", points, new_total, f"训练评分 {score}，时长 {duration} 秒"),
        )

        unlocked = []
        if new_level >= 2:
            unlocked.append("森林探索关卡")
        if new_level >= 3:
            unlocked.append("城市能量冲刺")
        if new_level >= 4:
            unlocked.append("多人排行榜挑战")
        if score >= 92:
            unlocked.append("标准动作徽章")
            badge = get_row("SELECT id FROM badges WHERE name = ? LIMIT 1", ("标准动作徽章",))
            if badge:
                try:
                    execute(
                        "INSERT INTO user_badges(user_id, badge_id) VALUES (?, ?)",
                        (user["id"], badge["id"]),
                    )
                except Exception:
                    pass
        return {"points": points, "total_points": new_total, "level": new_level, "unlocked": unlocked}


class ReportAgent:
    def build_report(self, user_id):
        sessions = list_rows(
            "SELECT * FROM sessions WHERE user_id = ? ORDER BY created_at DESC LIMIT 10",
            (user_id,),
        )
        if not sessions:
            return {
                "average": 0,
                "count": 0,
                "summary": "暂无训练记录。建议先完成一次新手关卡，系统会生成动作质量、积分和下次训练建议。",
                "sessions": [],
            }

        average = round(sum(s["score"] for s in sessions) / len(sessions), 1)
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
        summary = (
            f"近 {len(sessions)} 次训练平均分 {average}，薄弱动作是 {weak['exercise_name']}。"
            "建议下次先完成低速分解训练，再进入节奏型游戏关卡。"
        )
        suggestion = (
            f"保持 {best['exercise_name']} 的训练优势；{weak['exercise_name']} 建议降低速度，"
            "重点观察膝髋角度、肩髋稳定和呼吸节奏。"
        )
        return {
            "average": average,
            "count": len(sessions),
            "weak_exercise": weak["exercise_name"],
            "best_exercise": best["exercise_name"],
            "summary": summary,
            "suggestion": suggestion,
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
        report = self.report.build_report(user["id"])
        rec = self.recommendation.recommend(user)
        return {
            "profile_summary": self.profile.summarize(user),
            "today_plan": self.recommendation.today_plan(user, report),
            "recommendations": rec,
            "report": report,
            "badges": self.badges(user["id"]),
            "point_logs": self.point_logs(user["id"]),
            "agent_flow": [
                {"name": "画像智能体", "status": "已分析", "detail": "同步年龄、体能、偏好和伤病标签"},
                {"name": "图谱推荐智能体", "status": "已推荐", "detail": "匹配用户-动作-场馆-环境关系"},
                {"name": "动作评估智能体", "status": "待训练", "detail": "训练后生成动作评分和纠错建议"},
                {"name": "游戏激励智能体", "status": "待结算", "detail": "训练后结算积分、等级和解锁内容"},
                {"name": "报告智能体", "status": "已汇总", "detail": "根据历史训练生成趋势和建议"},
            ],
            "tips": list_rows("SELECT * FROM tips ORDER BY id DESC LIMIT 5"),
            "notifications": self.user_notifications(),
        }

    def user_notifications(self):
        announcements = list_rows(
            """
            SELECT title, content, level, published_at AS created_at
            FROM system_announcements
            ORDER BY published_at DESC
            LIMIT 5
            """
        )
        return [
            {
                "title": item.get("title") or "系统公告",
                "content": item.get("content") or "",
                "level": item.get("level") or "info",
                "created_at": item.get("created_at"),
            }
            for item in announcements
        ]

    def submit_session(self, user_id, exercise_name, raw_score, duration):
        user = get_row("SELECT * FROM users WHERE id = ?", (user_id,))
        score, feedback = self.motion.evaluate(exercise_name, raw_score)
        game = self.game.settle(user, score, duration)
        execute(
            "INSERT INTO sessions(user_id, exercise_name, score, duration, points, feedback) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, exercise_name, score, duration, game["points"], feedback),
        )
        updated_user = get_row("SELECT * FROM users WHERE id = ?", (user_id,))
        rec = self.recommendation.recommend(updated_user, exercise_name)
        return {"score": score, "feedback": feedback, "game": game, "recommendations": rec}

    def exercises(self):
        rows = list_rows("SELECT * FROM exercises ORDER BY difficulty, id")
        return [{**row, "standard": __import__("json").loads(row["standard_json"])} for row in rows]

    def venues(self):
        return list_rows(
            """
            SELECT id, name, display_name, resolved_address, name_source, image_url, image_source,
                   image_attribution, source_id, location, latitude, longitude, leisure_type, sport_type,
                   kind, equipment, capacity, crowd_index, air_quality, open_hours, rating,
                   facility_count, density_score
            FROM venues
            ORDER BY crowd_index, air_quality
            """
        )

    def sessions(self, user_id):
        return list_rows(
            "SELECT * FROM sessions WHERE user_id = ? ORDER BY created_at DESC LIMIT 20",
            (user_id,),
        )

    def badges(self, user_id):
        badges = list_rows("SELECT * FROM badges ORDER BY id")
        earned = list_rows("SELECT badge_id, earned_at FROM user_badges WHERE user_id = ?", (user_id,))
        earned_map = {item["badge_id"]: item["earned_at"] for item in earned}
        return [
            {
                **badge,
                "earned": badge["id"] in earned_map,
                "earned_at": str(earned_map[badge["id"]]) if badge["id"] in earned_map else None,
            }
            for badge in badges
        ]

    def point_logs(self, user_id):
        return list_rows(
            "SELECT * FROM point_logs WHERE user_id = ? ORDER BY created_at DESC LIMIT 10",
            (user_id,),
        )

    def save_pose_record(self, body):
        return execute(
            """
            INSERT INTO pose_records(
                session_id, user_id, exercise_name, confidence, stability_score,
                knee_angle, hip_angle, shoulder_balance, raw_landmarks_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                body.get("session_id"),
                int(body["user_id"]),
                body.get("exercise_name", "未知动作"),
                float(body.get("confidence", 0)),
                float(body.get("stability_score", 0)),
                body.get("knee_angle"),
                body.get("hip_angle"),
                body.get("shoulder_balance"),
                body.get("raw_landmarks_json", ""),
            ),
        )
