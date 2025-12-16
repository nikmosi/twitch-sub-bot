from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from twitch_subs.application.watchlist_service import WatchlistService
from twitch_subs.domain.events import UserError
from twitch_subs.domain.models import (
    BroadcasterType,
    LoginReportInfo,
    LoginStatus,
    UserRecord,
)
from twitch_subs.infrastructure.event_bus.inmemory import InMemoryEventBus
from twitch_subs.infrastructure.error import AsyncTelegramNotifyError
from twitch_subs.infrastructure.notifier.telegram import TelegramNotifier
from twitch_subs.infrastructure.repository_sqlite import SqliteWatchlistRepository
from twitch_subs.infrastructure.telegram import TelegramWatchlistBot


class StubSession:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class StubBot:
    def __init__(self) -> None:
        self.sent: list[tuple[str, dict[str, Any]]] = []
        self.fail_next = False
        self.session = StubSession()

    async def send_message(self, **kwargs: Any) -> None:
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("boom")
        text = kwargs.pop("text")
        self.sent.append((text, kwargs))


class DummyDispatcher:
    def __init__(self) -> None:
        self.message = SimpleNamespace(register=self._register)
        self.registered: list[tuple[Any, tuple[Any, ...]]] = []
        self.started = False
        self.stopped = False

    def _register(self, handler: Any, *filters: Any) -> None:
        self.registered.append((handler, filters))

    async def start_polling(self, bot: Any, handle_signals: bool = False) -> None:
        assert handle_signals is False
        self.started = True
        self.bot = bot

    async def stop_polling(self) -> None:
        self.stopped = True


def make_service(tmp_path: Path) -> WatchlistService:
    repo = SqliteWatchlistRepository(f"sqlite:///{tmp_path / 'watch.db'}")
    return WatchlistService(repo)


def test_bot_duplicate_and_missing(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    bot = TelegramWatchlistBot(StubBot(), "1", service, event_bus=InMemoryEventBus())
    bot.handle_command("/add foo")

    assert type(bot.handle_command("/add foo")[0]) is UserError
    assert type(bot.handle_command("/remove bar")[0]) is UserError


def test_handle_command_unknown(tmp_path: Path) -> None:
    bot = TelegramWatchlistBot(
        StubBot(), "1", make_service(tmp_path), event_bus=InMemoryEventBus()
    )
    assert bot.handle_command("/foo") == "Unknown command"
    assert bot.handle_command("/list") == "Watchlist is empty"


def test_handle_list_with_users(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    bot = TelegramWatchlistBot(StubBot(), "1", service, event_bus=InMemoryEventBus())
    bot.handle_command("/add foo")

    result = bot.handle_command("/list")

    assert "foo" in result
    assert "https://www.twitch.tv/foo" in result


@pytest.mark.asyncio
async def test_notifier_notify_report_sorts_and_formats() -> None:
    bot = StubBot()
    notifier = TelegramNotifier(bot, "chat")
    states = [
        LoginReportInfo(login="foo", broadcaster=BroadcasterType.PARTNER),
        LoginReportInfo(login="bar", broadcaster=BroadcasterType.NONE),
    ]

    await notifier.notify_report(states, checks=5, errors=1)

    assert bot.sent
    message, kwargs = bot.sent[0]
    assert "Checks: <b>5</b>" in message
    assert "Errors: <b>1</b>" in message
    assert message.index("bar") < message.index("foo")
    assert kwargs["disable_notification"] is True


@pytest.mark.asyncio
async def test_notifier_notify_about_change_uses_display_name() -> None:
    bot = StubBot()
    notifier = TelegramNotifier(bot, "chat")
    user = UserRecord(
        id="1",
        login="foo",
        display_name="FooBar",
        broadcaster_type=BroadcasterType.AFFILIATE,
    )
    status = LoginStatus(
        login="foo", broadcaster_type=BroadcasterType.NONE, user=user
    )

    await notifier.notify_about_change(status, BroadcasterType.PARTNER)

    assert bot.sent
    message, _ = bot.sent[0]
    assert "FooBar" in message
    assert "partner" in message


@pytest.mark.asyncio
async def test_notifier_notify_start_and_stop() -> None:
    bot = StubBot()
    notifier = TelegramNotifier(bot, "chat")

    await notifier.notify_about_start()
    await notifier.notify_about_stop()

    assert len(bot.sent) == 2


@pytest.mark.asyncio
async def test_notifier_send_message_handles_errors() -> None:
    bot = StubBot()
    notifier = TelegramNotifier(bot, "chat")

    bot.fail_next = True
    with pytest.raises(AsyncTelegramNotifyError):
        await notifier.send_message("oops")

    assert bot.fail_next is False


def test_run_polling_uses_asyncio_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    service = make_service(tmp_path)
    watch_bot = TelegramWatchlistBot(
        StubBot(), "1", service, event_bus=InMemoryEventBus()
    )
    called: dict[str, object] = {}

    def fake_run(coro) -> None:
        called["coro"] = coro
        coro.close()

    monkeypatch.setattr("twitch_subs.infrastructure.telegram.bot.asyncio.run", fake_run)

    watch_bot.run_polling()

    assert "coro" in called


@pytest.mark.asyncio
async def test_run_and_stop(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    dispatcher = DummyDispatcher()
    monkeypatch.setattr(
        "twitch_subs.infrastructure.telegram.bot.Dispatcher", lambda: dispatcher
    )
    bot = StubBot()
    service = make_service(tmp_path)
    watch_bot = TelegramWatchlistBot(bot, "1", service, event_bus=InMemoryEventBus())

    async def runner() -> None:
        await asyncio.wait_for(watch_bot.run(), timeout=0.1)

    task = asyncio.create_task(runner())
    await asyncio.sleep(0)
    await watch_bot.stop()
    await task

    assert dispatcher.started and dispatcher.stopped
    assert bot.session.closed
