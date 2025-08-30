import threading
from pathlib import Path
from threading import Event, Thread
from typing import Any, Sequence

import pytest
from typer.testing import CliRunner

import twitch_subs.container as container_mod
from twitch_subs import cli
from twitch_subs.application.logins import LoginsProvider
from twitch_subs.domain.models import State, TwitchAppCreds
from twitch_subs.infrastructure.repository_sqlite import SqliteWatchlistRepository


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


class DummyBot:
    def __init__(self, token: str, id: str, service: Any | None = None) -> None:  # noqa: D401
        _ = token
        _ = service
        _ = id

    async def run(self) -> None:  # noqa: D401
        pass


def test_cli_watch_invokes_watcher(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Set required environment variables
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    monkeypatch.setenv("TWITCH_CLIENT_ID", "id")
    monkeypatch.setenv("TWITCH_CLIENT_SECRET", "secret")

    # Provide fake implementations for dependencies
    class DummyTwitch:
        @classmethod
        def from_creds(cls, creds: TwitchAppCreds):  # noqa: D401
            _ = creds
            return cls()

    class DummyStateRepo:
        def load(self) -> State:  # noqa: D401
            return State()

        def save(self, state: State) -> None:  # noqa: D401
            _ = state
            pass

    monkeypatch.setattr(container_mod, "TwitchClient", DummyTwitch)
    monkeypatch.setattr("twitch_subs.infrastructure.twitch.TwitchClient", DummyTwitch)
    monkeypatch.setattr(container_mod, "TelegramNotifier", DummyNotifier)
    monkeypatch.setattr(container_mod, "TelegramWatchlistBot", DummyBot)
    monkeypatch.setattr(
        container_mod, "MemoryStateRepository", lambda: DummyStateRepo()
    )

    calls: dict[str, Any] = {}

    def fake_watch(
        self: container_mod.Watcher,
        logins: LoginsProvider | Sequence[str],
        interval: int,
        stop_event: Event,
        report_interval: int = 86400,
    ) -> None:  # noqa: D401
        _ = self
        _ = report_interval
        calls["logins"] = logins.get() if isinstance(logins, LoginsProvider) else logins
        calls["interval"] = interval
        stop_event.set()

    monkeypatch.setattr(container_mod.Watcher, "watch", fake_watch, raising=False)

    def fake_run_bot(bot: Any, stop: Event) -> None:  # noqa: D401
        _ = bot
        stop.set()

    monkeypatch.setattr(cli, "run_bot", fake_run_bot)

    runner = CliRunner()
    db = tmp_path / "db.sqlite"
    repo = SqliteWatchlistRepository(f"sqlite:///{db}")
    repo.add("foo")
    repo.add("bar")
    monkeypatch.setenv("DB_URL", f"sqlite:///{db}")
    result = runner.invoke(cli.app, ["watch", "--interval", "1"])
    assert result.exit_code == 0
    assert calls["logins"] == ["bar", "foo"] or calls["logins"] == ["foo", "bar"]
    assert set(calls["logins"]) == {"foo", "bar"}
    assert calls["interval"] == 1


def test_cli_graceful_shutdown_sets_stop_and_joins(
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
    monkeypatch.setattr(container_mod, "TelegramNotifier", DummyNotifier)
    monkeypatch.setattr(container_mod, "TelegramWatchlistBot", DummyBot)

    thread_ref: dict[str, Thread] = {}
    stop_holder: dict[str, Event] = {}

    def fake_watch(
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
        thread_ref["thread"] = threading.current_thread()
        stop_holder["event"] = stop_event
        stop_event.wait()

    monkeypatch.setattr(container_mod.Watcher, "watch", fake_watch, raising=False)

    def fake_run_bot(bot: Any, stop: Event) -> None:  # noqa: D401
        _ = bot
        stop.set()

    monkeypatch.setattr(cli, "run_bot", fake_run_bot)

    runner = CliRunner()
    db = tmp_path / "db.sqlite"
    repo = SqliteWatchlistRepository(f"sqlite:///{db}")
    repo.add("foo")
    monkeypatch.setenv("DB_URL", f"sqlite:///{db}")
    result = runner.invoke(cli.app, ["watch"])
    assert result.exit_code == 0
    assert stop_holder["event"].is_set()
    assert thread_ref["thread"] is not None and not thread_ref["thread"].is_alive()


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
    notifier = cli._get_notifier()  # pyright: ignore
    assert isinstance(notifier, cli.TelegramNotifier)
    assert notifier.token == "t" and notifier.chat_id == "c"
