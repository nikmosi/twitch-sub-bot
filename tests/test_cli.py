from pathlib import Path
from types import NoneType
from typing import Any

from pytest import MonkeyPatch
from typer.testing import CliRunner

from twitch_subs import cli
from twitch_subs.domain.models import TwitchAppCreds
from twitch_subs.infrastructure import watchlist


def test_cli_watch_invokes_watcher(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    # Set required environment variables
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    monkeypatch.setenv("TWITCH_CLIENT_ID", "id")
    monkeypatch.setenv("TWITCH_CLIENT_SECRET", "secret")

    # Avoid loading actual .env file
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)

    # Provide fake implementations for dependencies
    class DummyTwitch:
        @classmethod
        def from_creds(cls, creds: TwitchAppCreds):  # noqa: D401
            _ = creds
            return cls()

    class DummyNotifier:
        def __init__(self, token: str, chat_id: str) -> None:  # noqa: D401
            self.token = token
            self.chat_id = chat_id

        def send_message(
            self,
            text: str,
            disable_web_page_preview: bool = True,
            disable_notification: bool = False,
        ) -> None:  # noqa: D401
            _ = text
            _ = disable_web_page_preview
            _ = disable_notification
            pass

    class DummyStateRepo:
        def load(self) -> dict[str, Any]:  # noqa: D401
            return {}

        def save(self, state: dict[str, Any]) -> None:  # noqa: D401
            _ = state
            pass

    monkeypatch.setattr(cli, "TwitchClient", DummyTwitch)
    monkeypatch.setattr(cli, "TelegramNotifier", DummyNotifier)
    monkeypatch.setattr(cli, "StateRepository", lambda: DummyStateRepo())

    calls: dict[str, Any] = {}

    def fake_watch(
        self: cli.Watcher,
        logins: Any,
        interval: int,
        stop_event: NoneType = None,
        report_interval: int = 86400,
    ):  # noqa: D401
        _ = self
        _ = stop_event
        _ = report_interval
        calls["logins"] = logins.get() if hasattr(logins, "get") else logins
        calls["interval"] = interval

    monkeypatch.setattr(cli.Watcher, "watch", fake_watch, raising=False)

    runner = CliRunner()
    tmp_watch = tmp_path / "watch.json"
    watchlist.save(tmp_watch, ["foo", "bar"])
    monkeypatch.setenv("TWITCH_SUBS_WATCHLIST", str(tmp_watch))
    result = runner.invoke(cli.app, ["watch", "--interval", "1"])
    assert result.exit_code == 0
    assert calls["logins"] == ["bar", "foo"] or calls["logins"] == ["foo", "bar"]
    assert set(calls["logins"]) == {"foo", "bar"}
    assert calls["interval"] == 1
