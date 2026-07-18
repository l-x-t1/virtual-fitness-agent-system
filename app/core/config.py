import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv() -> None:
    env_file = Path(__file__).resolve().parents[2] / ".env"
    if not env_file.exists():
        return
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_dotenv()


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
    llm_provider: str = os.getenv("LLM_PROVIDER", "deepseek")
    model_name: str = os.getenv("MODEL_NAME", "")
    deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
    deepseek_base_url: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    dashscope_api_key: str = os.getenv("DASHSCOPE_API_KEY", "")
    dashscope_base_url: str = os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    llm_temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.2"))
    llm_timeout: int = int(os.getenv("LLM_TIMEOUT", "60"))


settings = Settings()
