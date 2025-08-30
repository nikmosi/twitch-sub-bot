from __future__ import annotations

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    twitch_client_id: str = Field(default=...)
    twitch_client_secret: str = Field(default=...)
    telegram_bot_token: str = Field(default=...)
    telegram_chat_id: str = Field(default=...)
    database_url: str = Field(
        default="sqlite:///./var/data.db", validation_alias="DB_URL"
    )
    database_echo: bool = Field(default=False, validation_alias="DB_ECHO")

    @field_validator("database_echo", mode="before")
    @classmethod
    def _parse_db_echo(cls, v: bool | str) -> bool:
        if v == "":
            return False
        return bool(v)

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
