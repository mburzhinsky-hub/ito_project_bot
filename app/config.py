from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    telegram_bot_token: SecretStr
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-4.1-mini"
    database_url: str = "sqlite+aiosqlite:///./data/bot.db"
    default_timezone: str = "Europe/Moscow"
    default_digest_time: str = "18:00"
    message_retention_days: int = Field(default=90, ge=1)
    unanswered_question_after_hours: int = Field(default=12, ge=1)
    deadline_reminder_hours: int = Field(default=24, ge=1)
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
