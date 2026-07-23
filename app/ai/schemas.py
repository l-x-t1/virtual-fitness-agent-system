from pydantic import BaseModel, Field


class TrainingExercise(BaseModel):
    name: str
    sets: int = Field(ge=1, le=10)
    reps: str
    rest_seconds: int = Field(ge=0, le=600)
    intensity: str
    notes: str = ""


class TrainingPlan(BaseModel):
    title: str
    goal: str
    duration_minutes: int = Field(ge=5, le=180)
    warmup: list[str] = Field(default_factory=list)
    exercises: list[TrainingExercise] = Field(default_factory=list)
    cooldown: list[str] = Field(default_factory=list)
    safety_notes: list[str] = Field(default_factory=list)


class UserProfile(BaseModel):
    fitness_level: str
    goals: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    habits: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    improvement_areas: list[str] = Field(default_factory=list)
    metrics: dict[str, float | int | str] = Field(default_factory=dict)
    summary: str
