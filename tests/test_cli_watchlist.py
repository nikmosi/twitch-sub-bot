from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from dependency_injector import providers
from typer.testing import CliRunner

import twitch_subs.container as container_mod
from twitch_subs import cli
from twitch_subs.application.event_handlers import register_notification_handlers
from twitch_subs.application.watchlist_service import WatchlistService
from twitch_subs.config import Settings
from twitch_subs.domain.events import (
    DayChanged,
    LoopChecked,
    LoopCheckFailed,
    OnceChecked,
    UserAdded,
    UserBecomeSubscribtable,
    UserRemoved,
)
from twitch_subs.domain.models import BroadcasterType
from twitch_subs.infrastructure.repository_sqlite import SqliteWatchlistRepository


class DummyAiogramBot:
    def __init__(
        self,
        token: str,
        default: Any | None = None,
        session: Any | None = None,
    ) -> None:
        self.token = token
        self.default = default
        self.session = session

    async def close(self) -> None:
        return None


class StubEventBus:
    def __init__(self) -> None:
        self.published: list[Any] = []
        self.started = 0
        self.stopped = 0
        self.subscriptions: list[tuple[type[Any], Any]] = []

    async def publish(self, *events: Any) -> None:
        self.published.extend(events)

    async def start(self) -> None:
        self.started += 1

    async def stop(self) -> None:
        self.stopped += 1

    def subscribe(self, event_type: type[Any], handler: Any) -> None:
        self.subscriptions.append((event_type, handler))


@pytest.fixture(autouse=True)
def stubbed_container(monkeypatch: pytest.MonkeyPatch) -> StubEventBus:
    """Avoid connecting to external services during CLI runs."""

    stub_bus = StubEventBus()

    class CompatibleWatchlistRepository(SqliteWatchlistRepository):
        def get_list(self) -> list[str]:
            return super().list()

    class DummyProducer:
        async def __aenter__(self) -> "DummyProducer":
            return self

        async def __aexit__(self, *_: Any) -> None:
            return None

        async def start(self) -> None:  # pragma: no cover - no-op
            return None

        async def stop(self) -> None:  # pragma: no cover - no-op
            return None

        async def publish(self, *events: Any) -> None:
            stub_bus.published.extend(events)

    @asynccontextmanager
    async def _yield(obj: Any):
        yield obj

    async def fake_build_container(settings: Settings) -> container_mod.AppContainer:
        container = container_mod.AppContainer()
        container.container_config.from_pydantic(settings)

        repo = CompatibleWatchlistRepository(settings.database_url)

        container.rabbit_conn.override(providers.Resource(_yield, object()))
        container.event_bus_factory.override(providers.Resource(_yield, stub_bus))
        container.telegram_bot.override(
            providers.Resource(_yield, DummyAiogramBot("token"))
        )
        container.bot_app.override(providers.Resource(_yield, object()))
        container.producer.override(providers.Resource(_yield, DummyProducer()))
        container.watchlist_repo.override(providers.Object(repo))
        container.watchlist_service.override(
            providers.Factory(WatchlistService, repo=repo)
        )
        container.watcher.override(providers.Resource(_yield, "watcher"))
        container.settings.override(providers.Object(settings))

        await container.init_resources()
        return container

    monkeypatch.setattr(cli, "build_container", fake_build_container)

    return stub_bus


def run(command: list[str], monkeypatch: pytest.MonkeyPatch, db: Path):
    runner = CliRunner()
    monkeypatch.setenv("DB_URL", f"sqlite:///{db}")
    # Minimal required environment so Settings() does not fail.
    monkeypatch.setenv("TWITCH_CLIENT_ID", "id")
    monkeypatch.setenv("TWITCH_CLIENT_SECRET", "secret")
    if "TELEGRAM_BOT_TOKEN" not in os.environ:
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    if "TELEGRAM_CHAT_ID" not in os.environ:
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "")
    monkeypatch.setattr(container_mod, "Bot", DummyAiogramBot)
    return runner.invoke(cli.app, command)


def test_add_list_remove_happy(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    db = tmp_path / "wl.db"
    res = run(["add", "foo", "-n"], monkeypatch, db)
    assert res.exit_code == 0
    repo = SqliteWatchlistRepository(f"sqlite:///{db}")
    assert repo.list() == ["foo"]
    res = run(["list"], monkeypatch, db)
    assert res.exit_code == 0
    assert res.output.strip() == "foo"
    res = run(["remove", "foo", "-n"], monkeypatch, db)
    assert res.exit_code == 0
    assert (
        run(["list"], monkeypatch, db).output.strip()
        == "Watchlist is empty. Use 'add' to add usernames."
    )


def test_idempotent_add(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    db = tmp_path / "wl.db"
    run(["add", "foo", "-n"], monkeypatch, db)
    run(["add", "foo", "-n"], monkeypatch, db)
    repo = SqliteWatchlistRepository(f"sqlite:///{db}")
    assert repo.list() == ["foo"]


def test_remove_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    db = tmp_path / "wl.db"
    res = run(["remove", "foo", "-n"], monkeypatch, db)
    assert res.exit_code != 0
    assert "not found" in res.output
    res = run(["remove", "foo", "--quiet"], monkeypatch, db)
    assert res.exit_code == 0


def test_username_validation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    db = tmp_path / "wl.db"
    good = run(["add", "user_1", "-n"], monkeypatch, db)
    assert good.exit_code == 0
    bad = run(["add", "bad*name", "-n"], monkeypatch, db)
    assert bad.exit_code == 2


def test_remove_emits_user_removed_event(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    db = tmp_path / "wl.db"
    stub_bus = StubEventBus()

    @asynccontextmanager
    async def _yield(obj: Any):
        yield obj

    class DummyProducer:
        async def __aenter__(self) -> "DummyProducer":
            return self

        async def __aexit__(self, *_: Any) -> None:
            return None

        async def publish(self, *events: Any) -> None:
            stub_bus.published.extend(events)

    async def fake_build_container(settings: Settings) -> container_mod.AppContainer:
        container = container_mod.AppContainer()
        container.container_config.from_pydantic(settings)
        container.rabbit_conn.override(providers.Resource(_yield, object()))
        container.event_bus_factory.override(providers.Resource(_yield, stub_bus))
        container.telegram_bot.override(
            providers.Resource(_yield, DummyAiogramBot("token"))
        )
        container.producer.override(providers.Resource(_yield, DummyProducer()))
        container.settings.override(providers.Object(settings))
        return container

    monkeypatch.setattr(cli, "build_container", fake_build_container)

    add_res = run(["add", "foo"], monkeypatch, db)
    assert add_res.exit_code == 0

    remove_res = run(["remove", "foo"], monkeypatch, db)
    assert remove_res.exit_code == 0

    assert any(isinstance(event, UserAdded) for event in stub_bus.published)
    assert any(isinstance(event, UserRemoved) for event in stub_bus.published)


@pytest.mark.asyncio
async def test_register_notification_handlers_sends_messages() -> None:
    messages: list[str] = []
    notified: list[str] = []

    class FakeNotifier:
        async def send_message(self, text: str, **_: Any) -> None:
            messages.append(text)

        async def notify_about_change(self, status: Any, curr: Any) -> None:
            notified.append(f"{status.login}:{curr.value}")

        async def notify_report(self, *args: Any, **kwargs: Any) -> None:
            return None

        async def notify_about_start(self) -> None:
            return None

        async def notify_about_stop(self) -> None:
            return None

    class FakeRepo:
        def get_sub_state(self, login: str) -> Any:
            return SimpleNamespace(status=BroadcasterType.NONE)

    bus = StubEventBus()
    notifier = FakeNotifier()
    register_notification_handlers(bus, notifier, FakeRepo())

    # Extract handlers and invoke manually
    for event_type, handler in bus.subscriptions:
        if event_type is UserRemoved:
            await handler(UserRemoved(login="foo"))
        if event_type is UserAdded:
            await handler(UserAdded(login="bar"))
        if event_type is OnceChecked:
            await handler(
                OnceChecked(login="foo", current_state=BroadcasterType.PARTNER)
            )
        if event_type is LoopChecked:
            await handler(LoopChecked(logins=("foo", "bar")))
        if event_type is LoopCheckFailed:
            await handler(LoopCheckFailed(logins=("foo",), error="boom"))
        if event_type is DayChanged:
            await handler(DayChanged())
        if event_type is UserBecomeSubscribtable:
            await handler(
                UserBecomeSubscribtable(
                    login="foo", current_state=BroadcasterType.AFFILIATE
                )
            )

    assert set(messages) == {
        "➖ <code>foo</code> удалён из списка наблюдения",
        "➕ <code>bar</code> добавлен в список наблюдения",
    }
