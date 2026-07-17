from collections import Counter, defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime, timedelta

from sqlalchemy import case, desc, distinct, func, select
from sqlalchemy.orm import Session

from app.cache import cache_delete
from app.cache import cache_keys
from app.db.models import (
    AdminOperationLog,
    Badge,
    Dictionary,
    Exercise,
    FitnessEquipment,
    KnowledgeGraphEdge,
    PointLog,
    PoseRecord,
    SystemAnnouncement,
    Tip,
    TrainingSession,
    User,
    UserBadge,
    Venue,
)
from app.db.session import SessionLocal


@contextmanager
def session_scope() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def row_dict(obj) -> dict | None:
    if obj is None:
        return None
    return {column.key: getattr(obj, column.key) for column in obj.__table__.columns}


def rows_dict(rows) -> list[dict]:
    return [row_dict(row) for row in rows]


def _today_range(days_ago: int = 0):
    start = datetime.combine(date.today() - timedelta(days=days_ago), datetime.min.time())
    return start, start + timedelta(days=1)


class FitnessRepository:
    def __init__(self, session: Session):
        self.session = session

    def user_by_id(self, user_id: int) -> dict | None:
        return row_dict(self.session.get(User, int(user_id)))

    def user_by_username(self, username: str) -> dict | None:
        stmt = select(User).where(User.username == username.strip())
        return row_dict(self.session.scalar(stmt))

    def create_user(self, username: str, password: str, nickname: str, **extra) -> int:
        user = User(username=username.strip(), password=password, nickname=nickname.strip(), **extra)
        self.session.add(user)
        self.session.flush()
        return user.id

    def update_user_password(self, user_id: int, password: str) -> None:
        user = self.session.get(User, int(user_id))
        if user:
            user.password = password
            cache_delete(*cache_keys.user_related(user.id))

    def update_profile(self, user_id: int, data: dict) -> dict | None:
        user = self.session.get(User, int(user_id))
        if not user:
            return None
        for key in ("age", "fitness_level", "injuries", "preference", "location"):
            if key in data:
                setattr(user, key, data[key])
        self.session.flush()
        cache_delete(*cache_keys.user_related(user.id))
        return row_dict(user)

    def settle_points(self, user_id: int, score: int, duration: int) -> dict:
        user = self.session.get(User, int(user_id))
        base = 10 + duration // 10
        bonus = 24 if score >= 92 else 16 if score >= 80 else 8 if score >= 65 else 4
        points = base + bonus
        user.points = (user.points or 0) + points
        user.level = max(user.level or 1, user.points // 120 + 1)
        self.session.add(PointLog(
            user_id=user.id,
            source_type="training",
            points_change=points,
            total_points=user.points,
            description=f"训练评分 {score}，时长 {duration} 秒",
        ))
        unlocked = []
        if user.level >= 2:
            unlocked.append("森林探索关卡")
        if user.level >= 3:
            unlocked.append("城市能量冲刺")
        if user.level >= 4:
            unlocked.append("多人排行榜挑战")
        if score >= 92:
            unlocked.append("标准动作徽章")
            badge = self.session.scalar(select(Badge).where(Badge.name == "标准动作徽章"))
            if badge:
                existing = self.session.scalar(select(UserBadge).where(UserBadge.user_id == user.id, UserBadge.badge_id == badge.id))
                if not existing:
                    self.session.add(UserBadge(user_id=user.id, badge_id=badge.id))
        cache_delete(*cache_keys.user_related(user.id), cache_keys.ADMIN_OVERVIEW)
        return {"points": points, "total_points": user.points, "level": user.level, "unlocked": unlocked}

    def add_session(self, user_id: int, exercise_name: str, score: int, duration: int, points: int, feedback: str) -> int:
        item = TrainingSession(user_id=user_id, exercise_name=exercise_name, score=score, duration=duration, points=points, feedback=feedback)
        self.session.add(item)
        self.session.flush()
        cache_delete(*cache_keys.user_related(user_id), cache_keys.ADMIN_OVERVIEW)
        return item.id

    def recent_sessions(self, user_id: int, limit: int = 20) -> list[dict]:
        stmt = select(TrainingSession).where(TrainingSession.user_id == int(user_id)).order_by(desc(TrainingSession.created_at)).limit(limit)
        return rows_dict(self.session.scalars(stmt).all())

    def add_pose_record(self, data: dict) -> int:
        item = PoseRecord(
            session_id=data.get("session_id"),
            user_id=int(data["user_id"]),
            exercise_name=data.get("exercise_name", "未知动作"),
            confidence=float(data.get("confidence", 0)),
            stability_score=float(data.get("stability_score", 0)),
            knee_angle=data.get("knee_angle"),
            hip_angle=data.get("hip_angle"),
            shoulder_balance=data.get("shoulder_balance"),
            raw_landmarks_json=data.get("raw_landmarks_json", ""),
        )
        self.session.add(item)
        self.session.flush()
        return item.id

    def exercises(self, limit: int | None = None) -> list[dict]:
        stmt = select(Exercise).order_by(Exercise.difficulty, Exercise.id)
        if limit:
            stmt = stmt.limit(limit)
        return rows_dict(self.session.scalars(stmt).all())

    def venues(self, limit: int | None = None, admin_fields: bool = False) -> list[dict]:
        stmt = select(Venue).order_by(Venue.crowd_index, Venue.air_quality)
        if admin_fields:
            stmt = select(Venue).order_by(desc(Venue.id))
        if limit:
            stmt = stmt.limit(limit)
        return rows_dict(self.session.scalars(stmt).all())

    def equipment_with_venue(self, order_by_usage: bool = False, limit: int | None = None) -> list[dict]:
        stmt = select(FitnessEquipment, Venue.name.label("venue_name")).join(Venue, FitnessEquipment.venue_id == Venue.id, isouter=True)
        if order_by_usage:
            stmt = stmt.order_by(desc(FitnessEquipment.crowd_index), desc(FitnessEquipment.daily_uses))
        else:
            stmt = stmt.order_by(desc(FitnessEquipment.updated_at), desc(FitnessEquipment.id))
        if limit:
            stmt = stmt.limit(limit)
        result = []
        for equipment, venue_name in getattr(self.session, "execute")(stmt).all():
            row = row_dict(equipment)
            row["venue_name"] = venue_name
            result.append(row)
        return result

    def equipment_stats(self) -> dict:
        stmt = select(
            func.count(FitnessEquipment.id).label("total_count"),
            func.sum(case((FitnessEquipment.is_smart.is_(True), 1), else_=0)).label("smart_count"),
            func.round(func.avg(FitnessEquipment.crowd_index), 1).label("average_crowd"),
            func.sum(case((FitnessEquipment.crowd_index >= 70, 1), else_=0)).label("high_density_count"),
            func.coalesce(func.sum(FitnessEquipment.daily_uses), 0).label("daily_uses"),
        )
        return dict(getattr(self.session, "execute")(stmt).mappings().one())

    def equipment_categories(self) -> list[dict]:
        count_expr = func.count().label("count")
        stmt = (
            select(FitnessEquipment.category, count_expr, func.round(func.avg(FitnessEquipment.crowd_index), 1).label("average_crowd"))
            .group_by(FitnessEquipment.category)
            .order_by(count_expr.desc())
        )
        return [dict(row) for row in getattr(self.session, "execute")(stmt).mappings().all()]

    def knowledge_edges(self, limit: int | None = None) -> list[dict]:
        stmt = select(KnowledgeGraphEdge).order_by(desc(KnowledgeGraphEdge.id))
        if limit:
            stmt = stmt.limit(limit)
        return rows_dict(self.session.scalars(stmt).all())

    def badges_for_user(self, user_id: int) -> list[dict]:
        badges = rows_dict(self.session.scalars(select(Badge).order_by(Badge.id)).all())
        earned = getattr(self.session, "execute")(select(UserBadge.badge_id, UserBadge.earned_at).where(UserBadge.user_id == int(user_id))).all()
        earned_map = {badge_id: earned_at for badge_id, earned_at in earned}
        for badge in badges:
            badge["earned"] = badge["id"] in earned_map
            badge["earned_at"] = str(earned_map[badge["id"]]) if badge["id"] in earned_map else None
        return badges

    def point_logs(self, user_id: int, limit: int = 10) -> list[dict]:
        stmt = select(PointLog).where(PointLog.user_id == int(user_id)).order_by(desc(PointLog.created_at)).limit(limit)
        return rows_dict(self.session.scalars(stmt).all())

    def tips(self, limit: int = 5) -> list[dict]:
        return rows_dict(self.session.scalars(select(Tip).order_by(desc(Tip.id)).limit(limit)).all())

    def notifications(self, limit: int = 5) -> list[dict]:
        stmt = select(SystemAnnouncement).order_by(desc(SystemAnnouncement.published_at)).limit(limit)
        rows = rows_dict(self.session.scalars(stmt).all())
        return [{"title": item.get("title") or "系统公告", "content": item.get("content") or "", "level": item.get("level") or "info", "created_at": item.get("published_at")} for item in rows]

    def admin_overview(self) -> dict:
        today_start, today_end = _today_range(0)
        yesterday_start, yesterday_end = _today_range(1)
        total_users = self.session.scalar(select(func.count()).select_from(User).where(User.role != "admin")) or 0
        total_equipment = self.session.scalar(select(func.count()).select_from(FitnessEquipment)) or 0
        online_equipment = self.session.scalar(select(func.count()).select_from(FitnessEquipment).where(FitnessEquipment.status == "normal")) or 0
        today_sessions = self.session.scalars(select(TrainingSession).where(TrainingSession.created_at >= today_start, TrainingSession.created_at < today_end)).all()
        yesterday_sessions = self.session.scalars(select(TrainingSession).where(TrainingSession.created_at >= yesterday_start, TrainingSession.created_at < yesterday_end)).all()
        users = self.session.scalars(select(User).where(User.role != "admin")).all()
        active_users = len({item.user_id for item in today_sessions})
        new_users_rows = self._daily_counts(User.created_at, 7)
        active_rows = self._daily_session_counts(distinct_users=True)
        session_rows = self._daily_session_counts(distinct_users=False)
        training_counter = Counter(item.exercise_name for item in today_sessions)
        return {
            "stats": {
                "total_users": total_users,
                "active_users": active_users,
                "total_sessions": len(today_sessions),
                "calories": sum(item.points for item in today_sessions),
                "online_equipment": online_equipment,
                "total_equipment": total_equipment,
                "yesterday_active_users": len({item.user_id for item in yesterday_sessions}),
                "yesterday_total_sessions": len(yesterday_sessions),
                "yesterday_calories": sum(item.points for item in yesterday_sessions),
            },
            "active_users": [row_dict(user) for user in sorted(users, key=lambda item: item.points or 0, reverse=True)[:8]],
            "recent_training": self.recent_training(8),
            "trend": {"new_users": new_users_rows, "active_users": active_rows, "sessions": session_rows},
            "training_types": [{"name": name, "count": count} for name, count in training_counter.most_common(8)],
            "operation_logs": self.admin_logs(8),
            "announcements": rows_dict(self.session.scalars(select(SystemAnnouncement).order_by(desc(SystemAnnouncement.published_at)).limit(5)).all()),
            "alerts": {
                "high_density": self.session.scalar(select(func.count()).select_from(Venue).where(Venue.crowd_index >= 70)) or 0,
                "maintenance": self.session.scalar(select(func.count()).select_from(FitnessEquipment).where(FitnessEquipment.status != "normal")) or 0,
            },
        }

    def _daily_counts(self, column, days: int) -> list[dict]:
        since = datetime.combine(date.today() - timedelta(days=days - 1), datetime.min.time())
        rows = getattr(self.session, "execute")(select(func.date(column).label("day"), func.count().label("count")).where(column >= since).group_by(func.date(column)).order_by("day")).all()
        return [{"day": str(day), "count": count} for day, count in rows]

    def _daily_session_counts(self, distinct_users: bool) -> list[dict]:
        since = datetime.combine(date.today() - timedelta(days=6), datetime.min.time())
        count_expr = func.count(distinct(TrainingSession.user_id)) if distinct_users else func.count()
        rows = getattr(self.session, "execute")(select(func.date(TrainingSession.created_at).label("day"), count_expr.label("count")).where(TrainingSession.created_at >= since).group_by(func.date(TrainingSession.created_at)).order_by("day")).all()
        return [{"day": str(day), "count": count} for day, count in rows]

    def recent_training(self, limit: int = 10) -> list[dict]:
        stmt = select(TrainingSession, User.nickname).join(User, TrainingSession.user_id == User.id).order_by(desc(TrainingSession.created_at)).limit(limit)
        return [{**row_dict(session), "nickname": nickname} for session, nickname in getattr(self.session, "execute")(stmt).all()]

    def admin_users(self) -> dict:
        users = rows_dict(self.session.scalars(select(User).order_by(desc(User.created_at))).all())
        role_rows = getattr(self.session, "execute")(select(User.role, func.count().label("count")).group_by(User.role)).all()
        user_ids_with_sessions = set(self.session.scalars(select(distinct(TrainingSession.user_id))).all())
        return {
            "users": users,
            "role_stats": [{"role": role, "count": count} for role, count in role_rows],
            "segment_stats": {
                "total_users": sum(1 for item in users if item.get("role") != "admin"),
                "active_users": len(user_ids_with_sessions),
                "new_users": sum(1 for item in users if item["id"] not in user_ids_with_sessions and item.get("role") != "admin"),
                "admin_users": sum(1 for item in users if item.get("role") == "admin"),
            },
        }

    def admin_user_detail(self, user_id: int) -> dict:
        user = self.user_by_id(user_id)
        return {
            "user": user,
            "stats": self.user_training_stats(user_id),
            "sessions": self.recent_sessions(user_id, 20),
        }

    def user_training_stats(self, user_id: int) -> dict:
        rows = self.session.scalars(select(TrainingSession).where(TrainingSession.user_id == int(user_id))).all()
        return {
            "session_count": len(rows),
            "average_score": round(sum(item.score for item in rows) / len(rows), 1) if rows else 0,
            "total_duration": sum(item.duration for item in rows),
            "total_points": sum(item.points for item in rows),
        }

    def admin_logs(self, limit: int = 50) -> list[dict]:
        stmt = select(AdminOperationLog, User.nickname.label("admin_name"), User.username.label("admin_username")).join(User, AdminOperationLog.admin_user_id == User.id, isouter=True).order_by(desc(AdminOperationLog.created_at)).limit(limit)
        return [{**row_dict(log), "admin_name": admin_name, "admin_username": admin_username} for log, admin_name, admin_username in getattr(self.session, "execute")(stmt).all()]

    def settings(self) -> list[dict]:
        stmt = select(Dictionary).where(Dictionary.dict_type == "admin_setting").order_by(Dictionary.sort_order, Dictionary.id)
        return rows_dict(self.session.scalars(stmt).all())

    def roles(self) -> list[dict]:
        stmt = select(Dictionary).where(Dictionary.dict_type == "admin_role").order_by(Dictionary.sort_order, Dictionary.id)
        return rows_dict(self.session.scalars(stmt).all())

    def upsert_dictionary(self, dict_type: str, key: str, value: str, enabled: bool = True, sort_order: int = 0) -> int:
        item = self.session.scalar(select(Dictionary).where(Dictionary.dict_type == dict_type, Dictionary.dict_key == key))
        if item:
            item.dict_value = value
            item.enabled = enabled
            item.sort_order = sort_order
        else:
            item = Dictionary(dict_type=dict_type, dict_key=key, dict_value=value, enabled=enabled, sort_order=sort_order)
            self.session.add(item)
        self.session.flush()
        cache_delete(cache_keys.ADMIN_OVERVIEW)
        return item.id

    def save_admin_log(self, admin_user_id: int | None, action: str, detail: str | None = None) -> int:
        item = AdminOperationLog(admin_user_id=admin_user_id, action=action, detail=detail)
        self.session.add(item)
        self.session.flush()
        cache_delete(cache_keys.ADMIN_OVERVIEW)
        return item.id

    def save_announcement(self, title: str, content: str, level: str = "info") -> int:
        item = SystemAnnouncement(title=title, content=content, level=level)
        self.session.add(item)
        self.session.flush()
        cache_delete(cache_keys.ADMIN_OVERVIEW)
        return item.id

    def save_exercise(self, data: dict) -> int:
        item = self.session.get(Exercise, int(data["id"])) if data.get("id") else self.session.scalar(select(Exercise).where(Exercise.name == data["name"]))
        if item:
            for key in ("name", "category", "difficulty", "target", "equipment", "standard_json"):
                if key in data:
                    setattr(item, key, data[key])
        else:
            item = Exercise(**{key: data[key] for key in ("name", "category", "difficulty", "target", "equipment", "standard_json")})
            self.session.add(item)
        self.session.flush()
        cache_delete(*cache_keys.CATALOG_KEYS)
        return item.id

    def save_equipment(self, data: dict) -> int:
        item = self.session.get(FitnessEquipment, int(data["id"])) if data.get("id") else None
        fields = ("name", "category", "venue_id", "location", "latitude", "longitude", "is_smart", "status", "manufacturer", "crowd_index", "daily_uses", "last_maintenance", "description")
        if item:
            for key in fields:
                if key in data:
                    setattr(item, key, data[key])
        else:
            item = FitnessEquipment(**{key: data.get(key) for key in fields if key in data})
            self.session.add(item)
        self.session.flush()
        cache_delete(*cache_keys.CATALOG_KEYS, cache_keys.ADMIN_OVERVIEW)
        return item.id

    def delete_equipment(self, equipment_id: int) -> None:
        item = self.session.get(FitnessEquipment, int(equipment_id))
        if item:
            self.session.delete(item)
            cache_delete(*cache_keys.CATALOG_KEYS, cache_keys.ADMIN_OVERVIEW)

    def save_venue(self, data: dict) -> int:
        item = self.session.get(Venue, int(data["id"])) if data.get("id") else self.session.scalar(select(Venue).where(Venue.name == data["name"]))
        fields = ("name", "source_id", "display_name", "resolved_address", "name_source", "image_url", "image_source", "image_attribution", "location", "latitude", "longitude", "leisure_type", "sport_type", "kind", "equipment", "capacity", "crowd_index", "air_quality", "open_hours", "rating", "facility_count", "density_score", "geometry_json")
        if item:
            for key in fields:
                if key in data:
                    setattr(item, key, data[key])
        else:
            item = Venue(**{key: data.get(key) for key in fields if key in data})
            self.session.add(item)
        self.session.flush()
        cache_delete(*cache_keys.CATALOG_KEYS, cache_keys.ADMIN_OVERVIEW)
        return item.id

    def delete_venue(self, venue_id: int) -> None:
        item = self.session.get(Venue, int(venue_id))
        if item:
            self.session.delete(item)
            cache_delete(*cache_keys.CATALOG_KEYS, cache_keys.ADMIN_OVERVIEW)

    def save_edge(self, data: dict) -> int:
        item = self.session.get(KnowledgeGraphEdge, int(data["id"])) if data.get("id") else None
        fields = ("source_type", "source_id", "source_name", "relation_type", "target_type", "target_id", "target_name", "weight", "note")
        if item:
            for key in fields:
                if key in data:
                    setattr(item, key, data[key])
        else:
            item = KnowledgeGraphEdge(**{key: data.get(key) for key in fields})
            self.session.add(item)
        self.session.flush()
        cache_delete(cache_keys.KNOWLEDGE_GRAPH)
        return item.id

    def delete_edge(self, edge_id: int) -> None:
        item = self.session.get(KnowledgeGraphEdge, int(edge_id))
        if item:
            self.session.delete(item)
            cache_delete(cache_keys.KNOWLEDGE_GRAPH)

    def save_user_admin(self, data: dict, password_hash: str | None = None) -> int:
        item = self.session.get(User, int(data["id"])) if data.get("id") else self.session.scalar(select(User).where(User.username == data["username"]))
        fields = ("username", "nickname", "age", "fitness_level", "injuries", "preference", "location", "role", "points", "level")
        if item:
            for key in fields:
                if key in data:
                    setattr(item, key, data[key])
            if password_hash:
                item.password = password_hash
        else:
            payload = {key: data.get(key) for key in fields if key in data}
            payload["password"] = password_hash or data.get("password") or "123456"
            item = User(**payload)
            self.session.add(item)
        self.session.flush()
        cache_delete(*cache_keys.user_related(item.id), cache_keys.ADMIN_OVERVIEW)
        return item.id

    def delete_user(self, user_id: int) -> None:
        item = self.session.get(User, int(user_id))
        if item:
            self.session.delete(item)
            cache_delete(*cache_keys.user_related(item.id), cache_keys.ADMIN_OVERVIEW)
