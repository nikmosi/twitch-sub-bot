import asyncio
from datetime import datetime, timezone
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from typing import Any, Sequence

import pytest
import typer
from typer.testing import CliRunner

import twitch_subs.container as container_mod
from twitch_subs import cli
from twitch_subs.config import Settings
from twitch_subs.application.logins import LoginsProvider
from twitch_subs.domain.models import BroadcasterType, SubState, TwitchAppCreds
from twitch_subs.infrastructure.repository_sqlite import (
    SqliteSubscriptionStateRepository,
)


class DummySession:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class DummyAiogramBot:
    def __init__(self, token: str, default: Any | None = None) -> None:  # noqa: D401
        self.token = token
        self.default = default
        self.session = DummySession()


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

    async def aclose(self) -> None:  # noqa: D401
        await self.bot.session.close()


class DummyBot:
    def __init__(self, bot: Any, id: str, service: Any | None = None) -> None:  # noqa: D401
        _ = bot
        _ = service
        _ = id

    async def run(self) -> None:  # noqa: D401
        pass


def configure_env(monkeypatch: pytest.MonkeyPatch, db: Path) -> None:
    monkeypatch.setenv("DB_URL", f"sqlite:///{db}")
    monkeypatch.setenv("TWITCH_CLIENT_ID", "id")
    monkeypatch.setenv("TWITCH_CLIENT_SECRET", "secret")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
def test_validate_usernames() -> None:
    assert cli.validate_usernames(["valid_name", "User123"]) == [
        "valid_name",
        "User123",
    ]
    with pytest.raises(typer.Exit) as exc:
        cli.validate_usernames(["bad-name"])
    assert exc.value.exit_code == 2


@pytest.mark.asyncio
async def test_run_watch_invokes_watcher() -> None:
    class DummyWatcher:
        def __init__(self) -> None:
            self.calls: list[tuple[list[str], int]] = []

        async def watch(
            self, logins: LoginsProvider, interval: int, stop_event: asyncio.Event
        ) -> None:
            self.calls.append((logins.get(), interval))
            stop_event.set()

    class Provider(LoginsProvider):
        def get(self) -> list[str]:
            return ["foo"]

    watcher = DummyWatcher()
    repo = SimpleNamespace(list=lambda: ["foo"])
    stop = asyncio.Event()
    await cli.run_watch(watcher, repo, interval=1, stop=stop)
    assert watcher.calls == [(["foo"], 1)]


@pytest.mark.asyncio
async def test_run_bot_waits_for_stop() -> None:
    class Bot:
        def __init__(self) -> None:
            self.started = False
            self.stopped = False

        async def run(self) -> None:
            self.started = True

        async def stop(self) -> None:
            self.stopped = True

    bot = Bot()
    stop = asyncio.Event()

    async def trigger() -> None:
        await asyncio.sleep(0)
        stop.set()

    trigger_task = asyncio.create_task(trigger())
    await cli.run_bot(bot, stop)
    await trigger_task
    assert bot.started and bot.stopped


def test_get_notifier_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TWITCH_CLIENT_ID", "id")
    monkeypatch.setenv("TWITCH_CLIENT_SECRET", "secret")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "")
    container = container_mod.Container(Settings())
    try:
        assert cli._get_notifier(container) is None
    finally:
        asyncio.run(container.aclose())


def test_get_notifier_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TWITCH_CLIENT_ID", "id")
    monkeypatch.setenv("TWITCH_CLIENT_SECRET", "secret")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "c")
    monkeypatch.setattr(container_mod, "Bot", DummyAiogramBot)
    container = container_mod.Container(Settings())
    try:
        notifier = cli._get_notifier(container)
        assert isinstance(notifier, cli.TelegramNotifier)
    finally:
        asyncio.run(container.aclose())


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


def test_state_get_and_list(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db = tmp_path / "state.db"
    configure_env(monkeypatch, db)
    repo = SqliteSubscriptionStateRepository(f"sqlite:///{db}")
    now = datetime.now(timezone.utc)
    repo.upsert_sub_state(
        SubState(
            "foo", True, BroadcasterType.AFFILIATE.value, since=now, updated_at=now
        )
    )
    repo.upsert_sub_state(SubState("bar", False, None, since=None, updated_at=now))

    runner = CliRunner()
    get_result = runner.invoke(cli.app, ["state", "get", "foo"])
    assert get_result.exit_code == 0
    assert "SubState" in get_result.output

    list_result = runner.invoke(cli.app, ["state", "list"])
    assert list_result.exit_code == 0
    assert "foo" in list_result.output and "bar" in list_result.output

    missing = runner.invoke(cli.app, ["state", "get", "missing"])
    assert missing.exit_code == 1


def test_state_list_empty(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db = tmp_path / "state-empty.db"
    configure_env(monkeypatch, db)
    runner = CliRunner()
    res = runner.invoke(cli.app, ["state", "list"])
    assert res.exit_code == 0
    assert "No subscription state found" in res.output


def test_watch_command_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db = tmp_path / "watch.db"
    configure_env(monkeypatch, db)

    class FakeRepo:
        def list(self) -> list[str]:
            return ["foo"]

    class FakeContainer:
        def __init__(self) -> None:
            self.settings = SimpleNamespace(
                telegram_bot_token="token", telegram_chat_id="chat"
            )
            self.watchlist_repo = FakeRepo()
            self.closed = False

        @property
        def watchlist_service(self) -> Any:
            return SimpleNamespace()

        def build_watcher(self) -> str:
            return "watcher"

        def build_bot(self) -> str:
            return "bot"

        async def aclose(self) -> None:
            self.closed = True

    fake_container = FakeContainer()
    monkeypatch.setattr(cli, "Container", lambda _: fake_container)

    calls = {"watch": False, "bot": False}

    async def fake_run_watch(
        watcher: Any, repo: Any, interval: int, stop: asyncio.Event
    ) -> None:
        calls["watch"] = True
        await asyncio.sleep(0)
        stop.set()

    async def fake_run_bot(bot: Any, stop: asyncio.Event) -> None:
        calls["bot"] = True
        await stop.wait()

    monkeypatch.setattr(cli, "run_watch", fake_run_watch)
    monkeypatch.setattr(cli, "run_bot", fake_run_bot)

    runner = CliRunner()
    result = runner.invoke(cli.app, ["watch", "--interval", "5"])

    assert result.exit_code == 0
    assert fake_container.closed
    assert calls["watch"]
    assert calls["bot"]
