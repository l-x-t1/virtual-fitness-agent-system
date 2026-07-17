from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    code: str = "OK"
    message: str = "success"
    data: T
    request_id: str


class ErrorResponse(BaseModel):
    code: str
    message: str
    details: list[Any] = Field(default_factory=list)
    request_id: str
