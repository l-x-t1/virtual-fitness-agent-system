"""数据模型统一出口。

SQLAlchemy ORM 模型定义在 ``app/db/models.py``，此处重导出，
让 ``app/models`` 同时承载 ORM 实体与 Pydantic 请求/响应模型，
满足分层目录约定。Pydantic schema 仍在各子模块（user/training/auth 等）。
"""

from app.db.models import (
    AdminOperationLog,
    AgentLog,
    Badge,
    BodyPart,
    Challenge,
    ChallengeRecord,
    Dictionary,
    EnvironmentSnapshot,
    Exercise,
    ExerciseStandard,
    FitnessEquipment,
    KnowledgeGraphEdge,
    Level,
    MotionMetric,
    PointLog,
    PoseRecord,
    RecommendationRecord,
    Report,
    SystemAnnouncement,
    Tip,
    TrainingSession,
    User,
    UserBadge,
    UserProfile,
    Venue,
)

__all__ = [
    "User",
    "UserProfile",
    "Exercise",
    "ExerciseStandard",
    "BodyPart",
    "Venue",
    "FitnessEquipment",
    "KnowledgeGraphEdge",
    "TrainingSession",
    "PoseRecord",
    "MotionMetric",
    "Tip",
    "Badge",
    "UserBadge",
    "Challenge",
    "AgentLog",
    "AdminOperationLog",
    "SystemAnnouncement",
    "EnvironmentSnapshot",
    "RecommendationRecord",
    "ChallengeRecord",
    "PointLog",
    "Level",
    "Report",
    "Dictionary",
]
