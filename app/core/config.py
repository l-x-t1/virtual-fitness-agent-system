import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    jwt_secret: str = os.getenv("JWT_SECRET", "development-only-change-this-32-byte-secret")
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = int(os.getenv("JWT_ACCESS_TOKEN_MINUTES", "30"))
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://postgres:postgres@localhost:5432/virtual_fitness_agent_system",
    )
    db_pool_size: int = int(os.getenv("DB_POOL_SIZE", "5"))
    db_max_overflow: int = int(os.getenv("DB_MAX_OVERFLOW", "10"))
    db_pool_timeout: int = int(os.getenv("DB_POOL_TIMEOUT", "30"))
    db_pool_recycle: int = int(os.getenv("DB_POOL_RECYCLE", "1800"))
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    cache_default_ttl: int = int(os.getenv("CACHE_DEFAULT_TTL", "300"))
    cache_lock_ttl: int = int(os.getenv("CACHE_LOCK_TTL", "8"))
    cors_origins: tuple[str, ...] = tuple(
        value.strip()
        for value in os.getenv("CORS_ORIGINS", "http://127.0.0.1:8765,http://localhost:8765").split(",")
        if value.strip()
    )


settings = Settings()
