from pydantic import BaseModel, Field


class ProfileUpdate(BaseModel):
    age: int = Field(default=20, ge=1, le=120)
    fitness_level: str = Field(default="beginner", max_length=30)
    injuries: str = Field(default="", max_length=500)
    preference: str = Field(default="综合训练", max_length=100)
    location: str = Field(default="校园东区", max_length=200)
