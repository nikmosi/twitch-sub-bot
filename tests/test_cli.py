from pathlib import Path
from threading import Event
from typing import Any, Sequence

import pytest
from typer.testing import CliRunner

import twitch_subs.container as container_mod
from twitch_subs import cli
from twitch_subs.application.logins import LoginsProvider
from twitch_subs.domain.models import TwitchAppCreds


class DummyAiogramBot:
    def __init__(self, token: str, default: Any | None = None) -> None:  # noqa: D401
        self.token = token
        self.default = default


class DummyNotifier:
    def __init__(self, bot: Any, chat_id: str) -> None:  # noqa: D401
        self.bot = bot
        self.token = getattr(bot, "token", "")
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


class DummyBot:
    def __init__(self, bot: Any, id: str, service: Any | None = None) -> None:  # noqa: D401
        _ = bot
        _ = service
        _ = id

    async def run(self) -> None:  # noqa: D401
        pass


def test_get_notifier_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TWITCH_CLIENT_ID", "id")
    monkeypatch.setenv("TWITCH_CLIENT_SECRET", "secret")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "")
    assert cli._get_notifier() is None  # pyright: ignore


def test_get_notifier_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TWITCH_CLIENT_ID", "id")
    monkeypatch.setenv("TWITCH_CLIENT_SECRET", "secret")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "c")
    monkeypatch.setattr(container_mod, "Bot", DummyAiogramBot)
    notifier = cli._get_notifier()  # pyright: ignore
    assert isinstance(notifier, cli.TelegramNotifier)


def test_watch_bot_exception_exitcode(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    monkeypatch.setenv("TWITCH_CLIENT_ID", "id")
    monkeypatch.setenv("TWITCH_CLIENT_SECRET", "secret")

    class DummyTwitch:
        @classmethod
        def from_creds(cls, creds: TwitchAppCreds):  # noqa: D401
            _ = creds
            return cls()

    monkeypatch.setattr(container_mod, "TwitchClient", DummyTwitch)
    monkeypatch.setattr("twitch_subs.infrastructure.twitch.TwitchClient", DummyTwitch)
    monkeypatch.setattr(container_mod, "Bot", DummyAiogramBot)
    monkeypatch.setattr(container_mod, "TelegramNotifier", DummyNotifier)
    monkeypatch.setattr(container_mod, "TelegramWatchlistBot", DummyBot)

    async def fake_watch(
        self: container_mod.Watcher,
        logins: LoginsProvider | Sequence[str],
        interval: int,
        stop_event: Event,
        report_interval: int = 86400,
    ) -> None:  # noqa: D401
        _ = self
        _ = logins
        _ = interval
        _ = report_interval
        stop_event.set()

    monkeypatch.setattr(container_mod.Watcher, "watch", fake_watch, raising=False)

    def fake_run_bot(bot: Any, stop: Event) -> None:
        _ = bot
        raise RuntimeError("boom")

    monkeypatch.setattr(cli, "run_bot", fake_run_bot)

    from loguru import logger

    logger.disable("twitch_subs.cli")

    try:
        runner = CliRunner()
        db = tmp_path / "db.sqlite"
        monkeypatch.setenv("DB_URL", f"sqlite:///{db}")
        result = runner.invoke(cli.app, ["watch"])
        assert result.exit_code == 1
    finally:
        logger.enable("twitch_subs.cli")


def test_cli_main_invokes_app(monkeypatch: pytest.MonkeyPatch) -> None:
    called: dict[str, bool] = {"done": False}

    class Dummy:
        def __call__(self) -> None:  # noqa: D401
            called["done"] = True

    monkeypatch.setattr(cli, "app", Dummy())
    cli.main()
    assert called["done"]
