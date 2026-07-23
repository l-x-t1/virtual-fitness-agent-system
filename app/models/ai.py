from typing import Any, Literal

from pydantic import BaseModel, Field


class AISessionCreate(BaseModel):
    title: str | None = Field(default=None, max_length=80)


class AIChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=2000)
    provider: Literal["deepseek", "dashscope", "bailian", "aliyun", "qwen"] | None = None
    model: str | None = Field(default=None, max_length=100)


class AIPlanRequest(BaseModel):
    goal: str | None = Field(default=None, max_length=200)
    duration_minutes: int = Field(default=25, ge=10, le=120)
    provider: Literal["deepseek", "dashscope", "bailian", "aliyun", "qwen"] | None = None
    model: str | None = Field(default=None, max_length=100)


class AICorrectionRequest(BaseModel):
    exercise_name: str = Field(min_length=1, max_length=100)
    score: int = Field(ge=0, le=100)
    pose_metrics: dict[str, Any] = Field(default_factory=dict)
    provider: Literal["deepseek", "dashscope", "bailian", "aliyun", "qwen"] | None = None
    model: str | None = Field(default=None, max_length=100)


class AIKnowledgeDocument(BaseModel):
    id: str | None = Field(default=None, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=10, max_length=10000)
    category: str = Field(default="custom", max_length=50)


class AIKnowledgeImportRequest(BaseModel):
    documents: list[AIKnowledgeDocument] = Field(min_length=1, max_length=100)


class AIProviderTestRequest(BaseModel):
    provider: Literal["deepseek", "dashscope", "bailian", "aliyun", "qwen"]
    model: str | None = Field(default=None, max_length=100)
