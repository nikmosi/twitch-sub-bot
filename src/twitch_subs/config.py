from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    twitch_client_id: str
    twitch_client_secret: str
    telegram_bot_token: str
    telegram_chat_id: str

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
