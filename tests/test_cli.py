from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Sequence

import pytest
import typer
from dependency_injector import providers
from typer.testing import CliRunner

import twitch_subs.container as container_mod
from twitch_subs import cli
from twitch_subs.application.logins import LoginsProvider
from twitch_subs.config import Settings
from twitch_subs.domain.models import BroadcasterType, SubState
from twitch_subs.infrastructure.repository_sqlite import (
    SqliteSubscriptionStateRepository,
)


class StubEventBus:
    def __init__(self) -> None:
        self.started = 0
        self.stopped = 0
        self.published: list[Any] = []
        self.subscriptions: list[tuple[type[Any], Any]] = []

    async def start(self) -> None:
        self.started += 1

    async def stop(self) -> None:
        self.stopped += 1

    async def publish(self, *events: Any) -> None:
        self.published.extend(events)

    def subscribe(self, event_type: type[Any], handler: Any) -> None:
        self.subscriptions.append((event_type, handler))


class DummySession:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class DummyAiogramBot:
    def __init__(self, token: str, session: Any, default: Any | None = None) -> None:
        self.token = token
        self.session = DummySession()
        self.default = default

    async def close(self) -> None:
        await self.session.close()


class DummyNotifier:
    def __init__(self, bot: Any, chat_id: str) -> None:
        self.bot = bot
        self.chat_id = chat_id

    async def aclose(self) -> None:
        await self.bot.session.close()


class DummyBot:
    async def run(self) -> None:  # pragma: no cover - behaviour mocked in tests
        return None

    async def stop(self) -> None:  # pragma: no cover - behaviour mocked in tests
        return None


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


def test_watch_bot_exception_exitcode(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    stub_bus = StubEventBus()
    dummy_notifier = DummyNotifier(DummyAiogramBot("token", object()), "chat")
    dummy_repo = SimpleNamespace(list=lambda: ["foo"])
    dummy_state_repo = SimpleNamespace(
        get_sub_state=lambda login: SubState(login, BroadcasterType.NONE)
    )

    class DummyWatcher:
        async def watch(
            self,
            logins: LoginsProvider | Sequence[str],
            interval: int,
            stop_event: asyncio.Event,
        ) -> None:
            stop_event.set()

    dummy_watcher = DummyWatcher()
    dummy_bot = DummyBot()

    async def fake_watch(
        self: container_mod.Watcher,
        logins: LoginsProvider | Sequence[str],
        interval: int,
        stop_event: asyncio.Event,
    ) -> None:
        stop_event.set()

    async def boom_bot(bot: Any, stop: asyncio.Event) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(container_mod.Watcher, "watch", fake_watch, raising=False)
    monkeypatch.setattr(cli, "run_bot", boom_bot)

    async def fake_build_container(settings: Settings) -> container_mod.AppContainer:
        container = container_mod.AppContainer()
        container.container_config.from_pydantic(settings)
        container.event_bus_factory.override(providers.Object(stub_bus))
        container.notifier.override(providers.Object(dummy_notifier))
        container.sub_state_repo.override(providers.Object(dummy_state_repo))
        container.watchlist_repo.override(providers.Object(dummy_repo))
        container.watcher.override(providers.Object(dummy_watcher))
        container.bot_app.override(providers.Object(dummy_bot))
        container.settings.override(providers.Object(settings))
        return container

    monkeypatch.setattr(cli, "build_container", fake_build_container)

    configure_env(monkeypatch, tmp_path / "db.sqlite")

    from loguru import logger

    logger.disable("twitch_subs.cli")
    try:
        runner = CliRunner()
        result = runner.invoke(cli.app, ["watch"])
        assert result.exit_code == 1
    finally:
        logger.enable("twitch_subs.cli")


def test_cli_main_invokes_app(monkeypatch: pytest.MonkeyPatch) -> None:
    called: dict[str, bool] = {"done": False}

    class Dummy:
        def __call__(self) -> None:
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
            "foo",
            BroadcasterType.AFFILIATE,
            since=now,
            updated_at=now,
        )
    )
    repo.upsert_sub_state(
        SubState("bar", BroadcasterType.NONE, since=None, updated_at=now)
    )

    async def fake_build_container(settings: Settings) -> container_mod.AppContainer:
        container = container_mod.AppContainer()
        container.container_config.from_pydantic(settings)
        container.sub_state_repo.override(providers.Object(repo))
        container.settings.override(providers.Object(settings))
        return container

    monkeypatch.setattr(cli, "build_container", fake_build_container)

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
    repo = SqliteSubscriptionStateRepository(f"sqlite:///{db}")

    async def fake_build_container(settings: Settings) -> container_mod.AppContainer:
        container = container_mod.AppContainer()
        container.container_config.from_pydantic(settings)
        container.sub_state_repo.override(providers.Object(repo))
        container.settings.override(providers.Object(settings))
        return container

    monkeypatch.setattr(cli, "build_container", fake_build_container)
    runner = CliRunner()
    res = runner.invoke(cli.app, ["state", "list"])
    assert res.exit_code == 0
    assert "No subscription state found" in res.output


def test_watch_command_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db = tmp_path / "watch.db"
    configure_env(monkeypatch, db)
    stub_bus = StubEventBus()

    class FakeNotifier:
        async def send_message(self, *args: Any, **kwargs: Any) -> None:  # noqa: D401
            return None

        async def notify_about_change(self, *args: Any, **kwargs: Any) -> None:  # noqa: D401
            return None

        async def notify_about_start(self) -> None:  # noqa: D401
            return None

        async def notify_about_stop(self) -> None:  # noqa: D401
            return None

        async def notify_report(self, *args: Any, **kwargs: Any) -> None:  # noqa: D401
            return None

    class FakeRepo:
        def list(self) -> list[str]:
            return ["foo"]

    class FakeStateRepo:
        def get_sub_state(self, login: str) -> SubState | None:  # noqa: D401
            return None

    fake_repo = FakeRepo()
    fake_notifier = FakeNotifier()
    fake_state_repo = FakeStateRepo()
    calls: dict[str, Any] = {}

    async def fake_run_watch(
        watcher: Any, repo: Any, interval: int, stop_event: asyncio.Event
    ) -> None:
        calls["watch"] = (watcher, repo.list(), interval)
        stop_event.set()

    async def fake_run_bot(bot: Any, stop_event: asyncio.Event) -> None:
        calls["bot"] = bot
        stop_event.set()

    monkeypatch.setattr(cli, "run_watch", fake_run_watch)
    monkeypatch.setattr(cli, "run_bot", fake_run_bot)

    async def fake_build_container(settings: Settings) -> container_mod.AppContainer:
        container = container_mod.AppContainer()
        container.container_config.from_pydantic(settings)
        container.event_bus_factory.override(providers.Object(stub_bus))
        container.watchlist_repo.override(providers.Object(fake_repo))
        container.notifier.override(providers.Object(fake_notifier))
        container.sub_state_repo.override(providers.Object(fake_state_repo))
        container.watcher.override(providers.Object("watcher"))
        container.bot_app.override(providers.Object("bot"))
        container.settings.override(providers.Object(settings))
        return container

    monkeypatch.setattr(cli, "build_container", fake_build_container)

    runner = CliRunner()
    result = runner.invoke(cli.app, ["watch", "--interval", "5"])

    assert result.exit_code == 0
    assert calls["watch"] == ("watcher", ["foo"], 5)
    assert calls["bot"] == "bot"
