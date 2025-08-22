from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    twitch_client_id: str = Field(default=...)
    twitch_client_secret: str = Field(default=...)
    telegram_bot_token: str = Field(default=...)
    telegram_chat_id: str = Field(default=...)

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
