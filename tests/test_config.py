from pathlib import Path

import pytest
from pydantic import ValidationError

from twitch_subs.config import Settings


def test_settings_reads_env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    env = tmp_path / ".env"
    env.write_text(
        "\n".join(
            [
                "TWITCH_CLIENT_ID=cid",
                "TWITCH_CLIENT_SECRET=secret",
                "TELEGRAM_BOT_TOKEN=bot",
                "TELEGRAM_CHAT_ID=chat",
            ]
        )
    )
    monkeypatch.chdir(str(tmp_path))
    settings = Settings()
    assert settings.twitch_client_id == "cid"
    assert settings.twitch_client_secret == "secret"
    assert settings.telegram_bot_token == "bot"
    assert settings.telegram_chat_id == "chat"


def test_settings_missing_fields(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    env = tmp_path / ".env"
    env.write_text("TWITCH_CLIENT_ID=cid")
    monkeypatch.chdir(str(tmp_path))
    with pytest.raises(ValidationError):
        Settings()


def test_settings_database_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TWITCH_CLIENT_ID", "id")
    monkeypatch.setenv("TWITCH_CLIENT_SECRET", "secret")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    settings = Settings()
    assert settings.database_url == "sqlite:///./var/data.db"
    assert settings.database_echo is False


def test_settings_database_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TWITCH_CLIENT_ID", "id")
    monkeypatch.setenv("TWITCH_CLIENT_SECRET", "secret")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    monkeypatch.setenv("DB_URL", "sqlite:///x.db")
    monkeypatch.setenv("DB_ECHO", "yes")
    settings = Settings()
    assert settings.database_url == "sqlite:///x.db"
    assert settings.database_echo is True


@pytest.mark.parametrize(
    "value, expected",
    [
        ("1", True),
        ("true", True),
        ("yes", True),
        ("0", False),
        ("no", False),
        ("", False),
    ],
)
def test_settings_database_echo_variants(
    monkeypatch: pytest.MonkeyPatch, value: str, expected: bool
) -> None:
    monkeypatch.setenv("TWITCH_CLIENT_ID", "id")
    monkeypatch.setenv("TWITCH_CLIENT_SECRET", "secret")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    monkeypatch.setenv("DB_ECHO", value)
    assert Settings().database_echo is expected
