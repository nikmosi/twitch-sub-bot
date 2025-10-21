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
    report_cron: str = Field(default="0 0 * * *", validation_alias="REPORT_CRON")
    rabbitmq_url: str | None = Field(default=None, validation_alias="RABBITMQ_URL")
    rabbitmq_exchange: str = Field(
        default="twitch_subs.events", validation_alias="RABBITMQ_EXCHANGE"
    )
    rabbitmq_queue: str | None = Field(
        default="twitch_subs.watcher", validation_alias="RABBITMQ_QUEUE"
    )
    rabbitmq_prefetch: int = Field(default=10, validation_alias="RABBITMQ_PREFETCH")

    @field_validator("database_echo", mode="before")
    @classmethod
    def _parse_db_echo(cls, v: bool | str) -> bool | str:
        if v == "":
            return False
        return v

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    task_timeout: int = 5
