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
    SubState,
    UserRecord,
)
from twitch_subs.infrastructure.event_bus.inmemory import InMemoryEventBus
from twitch_subs.infrastructure.error import NicknameExtractionError
from twitch_subs.infrastructure.notifier.telegram import TelegramNotifier
from twitch_subs.infrastructure.repository_sqlite import SqliteWatchlistRepository
from twitch_subs.infrastructure.telegram import TelegramWatchlistBot
from twitch_subs.infrastructure.telegram.bot import parse_twitch_usernames


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


class CompatibleWatchlistRepository(SqliteWatchlistRepository):
    def get_list(self) -> list[str]:
        return super().list()


def make_service(tmp_path: Path) -> WatchlistService:
    repo = CompatibleWatchlistRepository(f"sqlite:///{tmp_path / 'watch.db'}")
    return WatchlistService(repo)


def test_bot_duplicate_and_missing(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    bot = TelegramWatchlistBot(StubBot(), "1", service, event_bus=InMemoryEventBus())
    bot.handle_command("/add foo")

    err1 = bot.handle_command("/add foo")[0]
    assert type(err1) is UserError
    assert "already in the watchlist" in err1.exception

    err2 = bot.handle_command("/remove bar")[0]
    assert type(err2) is UserError
    assert "not found in the watchlist" in err2.exception


def test_handle_command_unknown(tmp_path: Path) -> None:
    bot = TelegramWatchlistBot(
        StubBot(), "1", make_service(tmp_path), event_bus=InMemoryEventBus()
    )
    assert bot.handle_command("/foo") == "❓ Unknown command"
    assert bot.handle_command("/list") == "📭 Watchlist is empty"


def test_handle_list_with_users(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    bot = TelegramWatchlistBot(StubBot(), "1", service, event_bus=InMemoryEventBus())
    bot.handle_command("/add foo")

    result = bot.handle_command("/list")

    assert "foo" in result
    assert "https://www.twitch.tv/foo" in result


def test_parse_twitch_usernames_handles_whitespace_and_urls() -> None:
    assert parse_twitch_usernames("foo   https://twitch.tv/bar\tbaz") == [
        "foo",
        "bar",
        "baz",
    ]


@pytest.mark.parametrize("text", ["юзер", "ab", "a" * 26])
def test_parse_twitch_usernames_rejects_invalid_logins(text: str) -> None:
    with pytest.raises(NicknameExtractionError) as exc:
        parse_twitch_usernames(text)

    assert "Could not extract a valid Twitch nickname" in str(exc.value)


@pytest.mark.asyncio
async def test_notifier_notify_report_sorts_and_formats() -> None:
    bot = StubBot()
    notifier = TelegramNotifier(bot, "chat")
    states = [
        SubState(login="foo", broadcaster_type=BroadcasterType.PARTNER),
        SubState(login="bar", broadcaster_type=BroadcasterType.NONE),
    ]

    await notifier.notify_report(states, checks=5, errors=1, missing_logins=("ghost",))

    if notifier._flush_task:
        await notifier._flush_task

    assert bot.sent
    message, kwargs = bot.sent[0]
    assert "Checks: <b>5</b>" in message
    assert "Errors: <b>1</b>" in message
    assert "Missing on Twitch:" in message
    assert "<code>ghost</code>" in message
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

    await notifier.notify_about_change(
        user.login,
        BroadcasterType.PARTNER,
        display_name=user.display_name,
    )

    if notifier._flush_task:
        await notifier._flush_task

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

    if notifier._flush_task:
        await notifier._flush_task

    assert len(bot.sent) == 1


@pytest.mark.asyncio
async def test_notifier_send_message_batches_messages() -> None:
    bot = StubBot()
    notifier = TelegramNotifier(bot, "chat")

    await notifier.send_message("msg1")
    await notifier.send_message("msg2")

    # Not sent yet
    assert not bot.sent

    if notifier._flush_task:
        await notifier._flush_task

    assert len(bot.sent) == 1
    message, _ = bot.sent[0]
    assert message == "msg1\nmsg2"


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
