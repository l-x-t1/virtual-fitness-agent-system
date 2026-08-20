from typing import Any

from pydantic import BaseModel, Field


class SessionSubmit(BaseModel):
    exercise_name: str = Field(min_length=1, max_length=100)
    score: int = Field(ge=0, le=100)
    duration: int = Field(ge=10)


class PoseRecordSubmit(BaseModel):
    exercise_name: str = Field(min_length=1, max_length=100)
    confidence: float = Field(default=0, ge=0, le=100)
    stability_score: float = Field(default=0, ge=0, le=100)
    knee_angle: float | None = None
    hip_angle: float | None = None
    shoulder_balance: float | None = None
    raw_landmarks_json: str = "{}"
    landmarks: list[dict[str, Any]] | None = Field(default=None, max_length=33)
    raw_score: float | None = Field(default=None, ge=0, le=100)
