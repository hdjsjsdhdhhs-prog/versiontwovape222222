from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = Field(alias="DATABASE_URL")
    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    admin_chat_id: str = Field(default="", alias="ADMIN_CHAT_ID")
    admin_username: str = Field(default="admin", alias="ADMIN_USERNAME")
    admin_password: str = Field(alias="ADMIN_PASSWORD")
    app_secret_key: str = Field(alias="APP_SECRET_KEY")
    admin_session_ttl_seconds: int = Field(default=60 * 60 * 24 * 7, alias="ADMIN_SESSION_TTL_SECONDS")
    public_base_url: str = Field(default="", alias="PUBLIC_BASE_URL")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
