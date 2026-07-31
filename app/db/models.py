from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    nickname: Mapped[str] = mapped_column(String(100), nullable=False)
    age: Mapped[int] = mapped_column(Integer, default=20)
    fitness_level: Mapped[str] = mapped_column(String(50), default="beginner")
    injuries: Mapped[str | None] = mapped_column(Text)
    preference: Mapped[str] = mapped_column(String(255), default="综合训练")
    location: Mapped[str] = mapped_column(String(255), default="校园东区")
    points: Mapped[int] = mapped_column(Integer, default=0)
    level: Mapped[int] = mapped_column(Integer, default=1)
    role: Mapped[str] = mapped_column(String(50), default="user")
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now())

    sessions = relationship("TrainingSession", back_populates="user", cascade="all, delete-orphan")


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    height_cm: Mapped[float | None] = mapped_column(Float)
    weight_kg: Mapped[float | None] = mapped_column(Float)
    bmi: Mapped[float | None] = mapped_column(Float)
    weekly_goal: Mapped[str | None] = mapped_column(Text)
    risk_level: Mapped[str] = mapped_column(String(50), default="low")
    preferred_time: Mapped[str | None] = mapped_column(String(100))
    updated_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


# 动作 ↔ 身体部位 多对多关联表（对应图谱 (Exercise)-[:INVOLVES]->(BodyPart)）
# 需定义在 Exercise 之前，供其 relationship secondary 引用
exercise_body_parts = Table(
    "exercise_body_parts",
    Base.metadata,
    Column("exercise_id", ForeignKey("exercises.id", ondelete="CASCADE"), primary_key=True),
    Column("body_part_id", ForeignKey("body_parts.id", ondelete="CASCADE"), primary_key=True),
)


class Exercise(Base):
    __tablename__ = "exercises"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    difficulty: Mapped[int] = mapped_column(Integer, nullable=False)
    target: Mapped[str] = mapped_column(String(255), nullable=False)
    equipment: Mapped[str] = mapped_column(String(255), nullable=False)
    standard_json: Mapped[str] = mapped_column(Text, nullable=False)

    body_parts = relationship("BodyPart", secondary=exercise_body_parts, back_populates="exercises")

    __table_args__ = (Index("idx_exercises_category", "category", "difficulty"),)


class BodyPart(Base):
    """身体部位：膝关节、髋部、核心、肩部等（对应图谱 BodyPart 节点）"""

    __tablename__ = "body_parts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now())

    exercises = relationship("Exercise", secondary=exercise_body_parts, back_populates="body_parts")


class ExerciseStandard(Base):
    __tablename__ = "exercise_standards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercises.id", ondelete="CASCADE"), nullable=False, index=True)
    metric_name: Mapped[str] = mapped_column(String(100), nullable=False)
    ideal_value: Mapped[float | None] = mapped_column(Float)
    min_value: Mapped[float | None] = mapped_column(Float)
    max_value: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(50))
    risk_hint: Mapped[str | None] = mapped_column(Text)


class Venue(Base):
    __tablename__ = "venues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    source_id: Mapped[str | None] = mapped_column(String(80), unique=True)
    display_name: Mapped[str | None] = mapped_column(String(160))
    resolved_address: Mapped[str | None] = mapped_column(String(255))
    name_source: Mapped[str | None] = mapped_column(String(80))
    image_url: Mapped[str | None] = mapped_column(String(500))
    image_source: Mapped[str | None] = mapped_column(String(255))
    image_attribution: Mapped[str | None] = mapped_column(String(255))
    location: Mapped[str] = mapped_column(String(255), nullable=False)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    leisure_type: Mapped[str | None] = mapped_column(String(80))
    sport_type: Mapped[str | None] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(50), default="outdoor")
    equipment: Mapped[str] = mapped_column(String(255), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    crowd_index: Mapped[int] = mapped_column(Integer, nullable=False)
    air_quality: Mapped[int] = mapped_column(Integer, nullable=False)
    open_hours: Mapped[str] = mapped_column(String(100), nullable=False)
    rating: Mapped[float] = mapped_column(Float, default=4.6)
    facility_count: Mapped[int] = mapped_column(Integer, default=1)
    density_score: Mapped[float] = mapped_column(Float, default=0)
    geometry_json: Mapped[str | None] = mapped_column(Text)

    equipment_items = relationship("FitnessEquipment", back_populates="venue")
    __table_args__ = (
        Index("idx_venues_location", "location"),
        Index("idx_venues_geo", "latitude", "longitude"),
        Index("idx_venues_crowd_density", "crowd_index", "density_score"),
    )


class FitnessEquipment(Base):
    __tablename__ = "fitness_equipment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    venue_id: Mapped[int | None] = mapped_column(ForeignKey("venues.id", ondelete="SET NULL"))
    location: Mapped[str] = mapped_column(String(255), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    is_smart: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(50), default="normal")
    manufacturer: Mapped[str | None] = mapped_column(String(120))
    crowd_index: Mapped[int] = mapped_column(Integer, default=0)
    daily_uses: Mapped[int] = mapped_column(Integer, default=0)
    last_maintenance: Mapped[object | None] = mapped_column(Date)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[object] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    venue = relationship("Venue", back_populates="equipment_items")
    __table_args__ = (
        Index("idx_equipment_venue", "venue_id", "category"),
        Index("idx_equipment_geo", "latitude", "longitude"),
        Index("idx_equipment_smart", "is_smart", "status"),
    )


class KnowledgeGraphEdge(Base):
    __tablename__ = "knowledge_graph_edges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_type: Mapped[str] = mapped_column(String(80), nullable=False)
    source_id: Mapped[int | None] = mapped_column(Integer)
    source_name: Mapped[str] = mapped_column(String(160), nullable=False)
    relation_type: Mapped[str] = mapped_column(String(80), nullable=False)
    target_type: Mapped[str] = mapped_column(String(80), nullable=False)
    target_id: Mapped[int | None] = mapped_column(Integer)
    target_name: Mapped[str] = mapped_column(String(160), nullable=False)
    weight: Mapped[float] = mapped_column(Float, default=1)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (Index("idx_kg_source", "source_type", "source_id"), Index("idx_kg_target", "target_type", "target_id"))


class TrainingSession(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    exercise_name: Mapped[str] = mapped_column(String(100), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    duration: Mapped[int] = mapped_column(Integer, nullable=False)
    points: Mapped[int] = mapped_column(Integer, nullable=False)
    feedback: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now())

    user = relationship("User", back_populates="sessions")
    __table_args__ = (Index("idx_sessions_user_time", "user_id", "created_at"),)


class PoseRecord(Base):
    __tablename__ = "pose_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("sessions.id", ondelete="SET NULL"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    exercise_name: Mapped[str] = mapped_column(String(100), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    stability_score: Mapped[float | None] = mapped_column(Float)
    knee_angle: Mapped[float | None] = mapped_column(Float)
    hip_angle: Mapped[float | None] = mapped_column(Float)
    shoulder_balance: Mapped[float | None] = mapped_column(Float)
    raw_landmarks_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (Index("idx_pose_records_user_time", "user_id", "created_at"),)


class MotionMetric(Base):
    __tablename__ = "motion_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    metric_name: Mapped[str] = mapped_column(String(100), nullable=False)
    metric_value: Mapped[float] = mapped_column(Float, nullable=False)
    score: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str | None] = mapped_column(String(50))
    correction_advice: Mapped[str | None] = mapped_column(Text)


class Tip(Base):
    __tablename__ = "tips"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tag: Mapped[str] = mapped_column(String(100), nullable=False)


class Badge(Base):
    __tablename__ = "badges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    condition_text: Mapped[str] = mapped_column(Text, nullable=False)
    icon: Mapped[str] = mapped_column(String(100), nullable=False)
    reward_points: Mapped[int] = mapped_column(Integer, default=0)


class UserBadge(Base):
    __tablename__ = "user_badges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    badge_id: Mapped[int] = mapped_column(ForeignKey("badges.id", ondelete="CASCADE"), nullable=False)
    earned_at: Mapped[object] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (UniqueConstraint("user_id", "badge_id", name="uq_user_badge"),)


class Challenge(Base):
    __tablename__ = "challenges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    exercise_name: Mapped[str] = mapped_column(String(100), nullable=False)
    goal_text: Mapped[str] = mapped_column(Text, nullable=False)
    difficulty: Mapped[int] = mapped_column(Integer, nullable=False)
    reward_points: Mapped[int] = mapped_column(Integer, nullable=False)
    scene: Mapped[str] = mapped_column(String(255), nullable=False)


class AgentLog(Base):
    __tablename__ = "agent_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[str] = mapped_column(String(255), nullable=False)
    result: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now())


class AdminOperationLog(Base):
    __tablename__ = "admin_operation_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    admin_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(255), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (Index("idx_admin_operation_logs_time", "created_at"),)


class SystemAnnouncement(Base):
    __tablename__ = "system_announcements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    level: Mapped[str] = mapped_column(String(50), default="info")
    published_at: Mapped[object] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (Index("idx_system_announcements_time", "published_at"),)


class EnvironmentSnapshot(Base):
    __tablename__ = "environment_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.id", ondelete="CASCADE"), nullable=False)
    crowd_index: Mapped[int] = mapped_column(Integer, nullable=False)
    air_quality: Mapped[int] = mapped_column(Integer, nullable=False)
    temperature: Mapped[float] = mapped_column(Float, nullable=False)
    weather: Mapped[str] = mapped_column(String(100), nullable=False)
    captured_at: Mapped[object] = mapped_column(DateTime, server_default=func.now())


class RecommendationRecord(Base):
    __tablename__ = "recommendation_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    recommendation_type: Mapped[str] = mapped_column(String(100), nullable=False)
    target_id: Mapped[int] = mapped_column(Integer, nullable=False)
    target_name: Mapped[str] = mapped_column(String(255), nullable=False)
    match_score: Mapped[float] = mapped_column(Float, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    agent_name: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now())


class ChallengeRecord(Base):
    __tablename__ = "challenge_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    challenge_id: Mapped[int] = mapped_column(ForeignKey("challenges.id", ondelete="CASCADE"), nullable=False)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("sessions.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    score: Mapped[int | None] = mapped_column(Integer)
    combo_count: Mapped[int] = mapped_column(Integer, default=0)
    completed_at: Mapped[object | None] = mapped_column(DateTime)


class PointLog(Base):
    __tablename__ = "point_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    source_type: Mapped[str] = mapped_column(String(100), nullable=False)
    source_id: Mapped[int | None] = mapped_column(Integer)
    points_change: Mapped[int] = mapped_column(Integer, nullable=False)
    total_points: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[object] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (Index("idx_point_logs_user_time", "user_id", "created_at"),)


class Level(Base):
    __tablename__ = "levels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    level: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    min_points: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    unlock_text: Mapped[str | None] = mapped_column(Text)


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    report_type: Mapped[str] = mapped_column(String(100), nullable=False)
    session_count: Mapped[int] = mapped_column(Integer, default=0)
    average_score: Mapped[float] = mapped_column(Float, default=0)
    weak_exercise: Mapped[str | None] = mapped_column(String(100))
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    suggestion: Mapped[str | None] = mapped_column(Text)
    generated_at: Mapped[object] = mapped_column(DateTime, server_default=func.now())


class Dictionary(Base):
    __tablename__ = "dictionaries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dict_type: Mapped[str] = mapped_column(String(100), nullable=False)
    dict_key: Mapped[str] = mapped_column(String(100), nullable=False)
    dict_value: Mapped[str] = mapped_column(String(255), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (Index("idx_dictionaries_type", "dict_type", "sort_order"),)
