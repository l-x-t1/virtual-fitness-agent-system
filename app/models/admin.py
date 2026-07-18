from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class AdminUserSave(BaseModel):
    id: int | None = Field(default=None, gt=0)
    username: str = Field(min_length=1, max_length=50)
    password: str | None = Field(default=None, min_length=6, max_length=128)
    nickname: str = Field(default="", max_length=50)
    role: Literal["user", "admin"] = "user"
    age: int = Field(default=30, ge=1, le=120)
    fitness_level: str = Field(default="beginner", max_length=30)
    preference: str = Field(default="综合训练", max_length=100)
    location: str = Field(default="石家庄市", max_length=200)


class EquipmentSave(BaseModel):
    id: int | None = Field(default=None, gt=0)
    name: str = Field(min_length=1, max_length=100)
    category: str = Field(min_length=1, max_length=100)
    venue_id: int | None = Field(default=None, gt=0)
    location: str = Field(min_length=1, max_length=200)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    is_smart: bool = False
    status: str = Field(default="normal", max_length=30)
    manufacturer: str = Field(default="", max_length=100)
    crowd_index: int = Field(default=0, ge=0, le=100)
    daily_uses: int = Field(default=0, ge=0)
    last_maintenance: date | None = None
    description: str = Field(default="", max_length=1000)


class VenueSave(BaseModel):
    id: int | None = Field(default=None, gt=0)
    name: str = Field(min_length=1, max_length=100)
    display_name: str | None = Field(default=None, max_length=100)
    location: str = Field(min_length=1, max_length=200)
    resolved_address: str | None = Field(default=None, max_length=300)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    sport_type: str = Field(default="fitness", max_length=50)
    leisure_type: str = Field(default="", max_length=50)
    kind: str = Field(default="indoor", max_length=30)
    equipment: str = Field(min_length=1, max_length=1000)
    capacity: int = Field(default=80, ge=0)
    crowd_index: int = Field(default=35, ge=0, le=100)
    air_quality: int = Field(default=60, ge=0, le=500)
    open_hours: str = Field(default="06:00-22:00", max_length=100)
    rating: float = Field(default=4.6, ge=0, le=5)
    facility_count: int = Field(default=1, ge=0)
    density_score: float | None = Field(default=None, ge=0, le=100)


class KnowledgeEdgeSave(BaseModel):
    id: int | None = Field(default=None, gt=0)
    source_type: str = Field(min_length=1, max_length=50)
    source_id: int | None = Field(default=None, gt=0)
    source_name: str = Field(min_length=1, max_length=100)
    relation_type: str = Field(min_length=1, max_length=100)
    target_type: str = Field(min_length=1, max_length=50)
    target_id: int | None = Field(default=None, gt=0)
    target_name: str = Field(min_length=1, max_length=100)
    weight: float = Field(default=1, ge=0)
    note: str = Field(default="", max_length=1000)


class AdminLogCreate(BaseModel):
    action: str = Field(default="后台操作", min_length=1, max_length=100)
    detail: str = Field(default="", max_length=1000)


class AnnouncementCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=5000)
    level: Literal["info", "warning", "error", "success"] = "info"


class AdminSettingsUpdate(BaseModel):
    settings: dict[str, bool]


class ExerciseSave(BaseModel):
    id: int | None = Field(default=None, gt=0)
    name: str = Field(min_length=1, max_length=100)
    category: str = Field(default="综合训练", max_length=100)
    difficulty: int = Field(default=2, ge=1, le=5)
    target: str = Field(default="全身协调", max_length=200)
    equipment: str = Field(default="徒手", max_length=200)
    duration: str = Field(default="20分钟", max_length=50)


class RolePermissions(BaseModel):
    users: str = "只读"
    training: str = "只读"
    courses: str = "只读"
    equipment: str = "只读"
    reports: str = "只读"
    system: str = "只读"


class RoleSave(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    key: str | None = Field(default=None, max_length=100)
    permissions: RolePermissions = Field(default_factory=RolePermissions)
    sort_order: int = Field(default=20, ge=0)
