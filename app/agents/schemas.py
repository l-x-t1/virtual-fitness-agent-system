from pydantic import BaseModel, Field


class ProfileInfo(BaseModel):
    fitness_level: str = Field(default="", description="User fitness level analysis.")
    preference: str = Field(default="", description="User exercise preference summary.")
    goal: str = Field(default="", description="Inferred fitness goal.")
    risk: str = Field(default="", description="Risk or injury warning.")


class ProfileOutput(BaseModel):
    profile: ProfileInfo


class RecommendationItem(BaseModel):
    name: str = Field(default="", description="Recommended exercise name.")
    reason: str = Field(default="", description="Why this item is recommended.")
    score: float = Field(default=0, description="Recommendation score from 0 to 100.")


class RecommendOutput(BaseModel):
    recommendations: list[RecommendationItem] = Field(default_factory=list)


class EvaluationInfo(BaseModel):
    score: float = Field(default=0, description="Motion quality score from 0 to 100.")
    mistakes: list[str] = Field(default_factory=list, description="Detected mistakes.")
    suggestions: list[str] = Field(default_factory=list, description="Correction suggestions.")


class EvaluateOutput(BaseModel):
    evaluation: EvaluationInfo


class MotivationOutput(BaseModel):
    message: str = Field(default="", description="Personalized encouragement message.")
    strategy: str = Field(default="", description="Motivation strategy.")
    next_goal: str = Field(default="", description="Next achievable training goal.")


class ReportOutput(BaseModel):
    title: str = Field(default="", description="Report title.")
    summary: str = Field(default="", description="Training summary.")
    analysis: str = Field(default="", description="Training analysis.")
    plan: list[str] = Field(default_factory=list, description="Next training plan.")
