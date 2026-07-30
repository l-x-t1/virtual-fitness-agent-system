from typing import Any, Literal

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=128)


class RegisterRequest(LoginRequest):
    nickname: str = Field(min_length=1, max_length=50)


class TokenUser(BaseModel):
    id: int
    username: str | None = None
    nickname: str | None = None
    role: str = "user"


class TokenResponse(BaseModel):
    access_token: str = Field(min_length=1)
    token_type: Literal["bearer"] = "bearer"
    expires_at: int = Field(gt=0)
    user: dict[str, Any]
