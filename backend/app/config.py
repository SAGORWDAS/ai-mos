from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./ai-mos.db"
    redis_url: str = "redis://localhost:6379/0"
    openrouter_api_key: str = ""
    token_encryption_key: str = ""
    allowed_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    public_api_url: str = "http://localhost:3000/api"
    secure_cookies: bool = False
    session_hours: int = 24
    provider_mode: Literal["sandbox", "openrouter"] = "sandbox"
    worker_enabled: bool = True
    worker_database_url: str = ""
    worker_poll_seconds: float = 0.5
    model_id: str = ""
    embedding_model_id: str = ""
    model_cache_seconds: int = Field(default=21600, ge=0, le=86400)
    model_max_cost_micros: int = Field(default=20000, ge=1, le=1_000_000)
    sandbox_model_cost_micros: int = Field(default=0, ge=0, le=1_000_000)
    sandbox_failure: str = ""
    payment_webhook_secret: str = "placeholder-local-test-secret-do-not-use-live"

    app_env: str = "development"
    sentry_dsn: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
