"""
图查询/响应的 Pydantic 模型（内部使用）
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class GraphExercise(BaseModel):
    exercise_id: int | None = None
    name: str
    category: str = ""
    difficulty: int = 1
    target: str = ""
    equipment: str = ""
    match_score: float = 0.0
    reason: str = ""


class GraphVenue(BaseModel):
    venue_id: int | None = None
    name: str
    location: str = ""
    latitude: float | None = None
    longitude: float | None = None
    crowd_index: int = 50
    air_quality: int = 50
    rating: float = 4.0
    density_score: float = 0.0
    equipment: str = ""
    capacity: int = 0
    kind: str = "outdoor"
    open_hours: str = ""
    distance_km: float | None = None
    match_score: float = 0.0


class GraphRecommendationResult(BaseModel):
    exercises: list[GraphExercise] = Field(default_factory=list)
    venues: list[GraphVenue] = Field(default_factory=list)


class GraphRAGResult(BaseModel):
    query: str = ""
    answer: str = ""
    cypher: str = ""
    exercises: list[GraphExercise] = Field(default_factory=list)
    venues: list[GraphVenue] = Field(default_factory=list)


class UserNodeInput(BaseModel):
    """创建/更新 User 节点所需的字段"""
    user_id: int
    nickname: str = ""
    age: int = 20
    fitness_level: str = "beginner"
    injuries: str = ""
    preference: str = "综合训练"
    location: str = ""
    points: int = 0
    level: int = 1


class ExerciseNodeInput(BaseModel):
    exercise_id: int
    name: str
    category: str
    difficulty: int
    target: str
    equipment: str
    standard_json: str = "{}"


class VenueNodeInput(BaseModel):
    venue_id: int
    name: str
    location: str
    latitude: float | None = None
    longitude: float | None = None
    equipment: str = ""
    capacity: int = 0
    crowd_index: int = 50
    air_quality: int = 50
    rating: float = 4.0
    density_score: float = 0.0
    kind: str = "outdoor"
    open_hours: str = ""


class EquipmentNodeInput(BaseModel):
    equipment_id: int
    name: str
    category: str = ""
    is_smart: bool = False
    status: str = "normal"
    location: str = ""
    latitude: float = 0.0
    longitude: float = 0.0
    venue_id: int | None = None
