import pytest
from pydantic import ValidationError

from twitch_subs.config import Settings


def test_settings_reads_env_file(tmp_path, monkeypatch):
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
    monkeypatch.chdir(tmp_path)
    settings = Settings()
    assert settings.twitch_client_id == "cid"
    assert settings.twitch_client_secret == "secret"
    assert settings.telegram_bot_token == "bot"
    assert settings.telegram_chat_id == "chat"


def test_settings_missing_fields(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("TWITCH_CLIENT_ID=cid")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValidationError):
        Settings()
