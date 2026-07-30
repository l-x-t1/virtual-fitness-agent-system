from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ProfileInfo(BaseModel):
    fitness_level: str
    goals: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    habits: list[str] = Field(default_factory=list)
    summary: str


class ProfileOutput(BaseModel):
    profile: ProfileInfo


class RecommendationItem(BaseModel):
    name: str
    score: float = Field(ge=0, le=100)
    reason: str
    risk_warning: str = ""


class RecommendOutput(BaseModel):
    recommendations: list[RecommendationItem] = Field(default_factory=list, max_length=5)


class EvaluationInfo(BaseModel):
    score: float = Field(ge=0, le=100)
    mistakes: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    risk_level: Literal["low", "medium", "high", "unknown"] = "unknown"


class EvaluateOutput(BaseModel):
    evaluation: EvaluationInfo


class MotivationOutput(BaseModel):
    message: str
    story: str
    strategy: str
    next_goal: str


class ReportOutput(BaseModel):
    report_type: Literal["weekly", "monthly"]
    empty: bool = False
    training_count: int = Field(ge=0)
    average_score: float = Field(ge=0, le=100)
    total_duration: float = Field(ge=0)
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    trend_analysis: str
    risk_reminders: list[str] = Field(default_factory=list)
    next_plan: list[str] = Field(default_factory=list)
    summary: str
