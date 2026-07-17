import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    jwt_secret: str = os.getenv("JWT_SECRET", "development-only-change-this-32-byte-secret")
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = int(os.getenv("JWT_ACCESS_TOKEN_MINUTES", "30"))
    cors_origins: tuple[str, ...] = tuple(
        value.strip()
        for value in os.getenv("CORS_ORIGINS", "http://127.0.0.1:8765,http://localhost:8765").split(",")
        if value.strip()
    )


settings = Settings()
