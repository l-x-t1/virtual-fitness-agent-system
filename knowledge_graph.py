import json
import math

from app.repositories import FitnessRepository, session_scope


class FitnessKnowledgeGraph:
    """Lightweight user-action-venue graph used by the recommendation agent."""

    DEFAULT_USER_COORD = (38.047, 114.514)

    def __init__(self):
        self.exercises = []
        self.venues = []
        self.refresh()

    def refresh(self):
        with session_scope() as session:
            repo = FitnessRepository(session)
            self.exercises = repo.exercises()
            self.venues = repo.venues()

    def recommend_exercises(self, user):
        level = user.get("fitness_level", "beginner")
        injuries = user.get("injuries", "") or ""
        preference = user.get("preference", "") or ""
        max_difficulty = 1 if level == "beginner" else 2 if level == "intermediate" else 3

        ranked = []
        for item in self.exercises:
            score = 70
            if item["difficulty"] <= max_difficulty:
                score += 15
            if item["category"] in preference or item["target"] in preference or item["name"] in preference:
                score += 10
            if "膝" in injuries and item["name"] in {"深蹲", "弓步蹲", "开合跳", "节奏冲刺"}:
                score -= 24
            if "腰" in injuries and item["name"] == "平板支撑":
                score -= 16
            if user.get("age", 20) >= 55 and item["difficulty"] >= 2:
                score -= 10
            reasons = []
            if item["difficulty"] <= max_difficulty:
                reasons.append("难度适合当前体能")
            if item["category"] in preference or item["target"] in preference or item["name"] in preference:
                reasons.append("符合运动偏好")
            if not reasons:
                reasons.append("动作基础性强，适合作为日常训练")
            ranked.append({
                **item,
                "standard": json.loads(item["standard_json"] or "{}"),
                "match_score": max(0, score),
                "reason": "；".join(reasons),
            })
        return sorted(ranked, key=lambda x: x["match_score"], reverse=True)[:5]

    def recommend_venues(self, user, exercise_name=None):
        preferred_equipment = ""
        if exercise_name:
            for exercise in self.exercises:
                if exercise["name"] == exercise_name:
                    preferred_equipment = exercise["equipment"]

        user_lat, user_lon = self._user_coord(user)
        ranked = []
        for venue in self.venues:
            venue_payload = {key: value for key, value in venue.items() if key != "geometry_json"}
            distance_km = self._distance_km(user_lat, user_lon, venue.get("latitude"), venue.get("longitude"))
            distance_penalty = min(distance_km * 1.8, 72) if distance_km is not None else 18
            density_penalty = min(float(venue.get("density_score") or 0) * 0.18, 16)
            score = 112 - venue["crowd_index"] * 0.55 - venue["air_quality"] * 0.14 - distance_penalty - density_penalty
            reasons = []
            if distance_km is not None and distance_km <= 3:
                score += 18
                reasons.append("距离很近")
            elif distance_km is not None and distance_km <= 8:
                score += 10
                reasons.append("周边可达")
            if user.get("location") and user["location"] in venue["location"]:
                score += 18
                reasons.append("位置匹配")
            if preferred_equipment and preferred_equipment in venue["equipment"]:
                score += 16
                reasons.append("器材匹配")
            if venue["crowd_index"] < 35:
                score += 14
                reasons.append("当前人流少")
            if venue["air_quality"] <= 50:
                reasons.append("空气质量适合户外训练")
            if not reasons:
                reasons.append("综合环境指标较均衡")
            ranked.append({
                **venue_payload,
                "address": venue.get("location"),
                "distance_km": round(distance_km, 2) if distance_km is not None else None,
                "distance": f"{distance_km:.1f}km" if distance_km is not None else "未知",
                "match_score": round(max(0, score), 1),
                "reason": "；".join(reasons),
            })
        nearby = [item for item in ranked if item.get("distance_km") is not None and item["distance_km"] <= 80]
        return sorted(nearby or ranked, key=lambda x: (x["match_score"], -x.get("crowd_index", 100)), reverse=True)[:120]

    def _user_coord(self, user):
        if user.get("current_lat") is not None and user.get("current_lon") is not None:
            return float(user["current_lat"]), float(user["current_lon"])
        location = user.get("location") or ""
        if "桥西" in location:
            return 38.034, 114.468
        if "裕华" in location:
            return 38.010, 114.533
        if "正定" in location:
            return 38.147, 114.570
        return self.DEFAULT_USER_COORD

    def _distance_km(self, lat1, lon1, lat2, lon2):
        if lat2 in (None, "") or lon2 in (None, ""):
            return None
        lat2 = float(lat2)
        lon2 = float(lon2)
        radius = 6371.0
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)
        a = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
        return radius * 2 * math.asin(math.sqrt(a))

    def next_level(self, user, recent_average):
        level = user.get("level", 1)
        if recent_average >= 88:
            return level + 1, "表现稳定优秀，下一关将提升动作组合难度。"
        if recent_average < 70:
            return max(1, level - 1), "动作质量需要巩固，下一关会降低节奏并增加提示。"
        return level, "保持当前难度，继续积累标准动作次数。"
