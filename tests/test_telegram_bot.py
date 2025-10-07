import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from twitch_subs.application.watchlist_service import WatchlistService
from twitch_subs.domain.models import (
    BroadcasterType,
    LoginReportInfo,
    LoginStatus,
    UserRecord,
)
from twitch_subs.infrastructure.repository_sqlite import SqliteWatchlistRepository
from twitch_subs.infrastructure.telegram import (
    IDFilter,
    TelegramNotifier,
    TelegramWatchlistBot,
)


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


def test_notifier_formats_messages(monkeypatch: pytest.MonkeyPatch) -> None:
    bot = StubBot()
    notifier = TelegramNotifier(bot, "123")

    user = UserRecord("1", "foo", "Foo", BroadcasterType.AFFILIATE)
    status = LoginStatus("foo", BroadcasterType.AFFILIATE, user)

    asyncio.run(notifier.notify_about_start())
    asyncio.run(notifier.notify_about_change(status, BroadcasterType.AFFILIATE))
    asyncio.run(
        notifier.notify_report(
            states=[LoginReportInfo(login="Foo", status="aff")],
            checks=5,
            errors=1,
        )
    )
    asyncio.run(notifier.notify_about_stop())
    asyncio.run(notifier.aclose())

    assert bot.sent[0][0].startswith("🟢")
    assert "Foo" in bot.sent[1][0]
    # notify_report batches and marks notification as silent
    assert any(kwargs.get("disable_notification") for _, kwargs in bot.sent)

    bot.fail_next = True
    asyncio.run(notifier.send_message("fails"))
    # failure swallowed, no new message recorded
    assert bot.sent[-1][0] != "fails"


def test_bot_duplicate_and_missing(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    bot = TelegramWatchlistBot(StubBot(), "1", service)
    bot.handle_command("/add foo")

    assert bot.handle_command("/add foo") == "foo already present"
    assert bot.handle_command("/remove bar") == "bar not found"


def test_handle_command_unknown(tmp_path: Path) -> None:
    bot = TelegramWatchlistBot(StubBot(), "1", make_service(tmp_path))
    assert bot.handle_command("/foo") == "Unknown command"
    assert bot.handle_command("/list") == "Watchlist is empty"


def test_id_filter_and_handlers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    service = make_service(tmp_path)
    bot = TelegramWatchlistBot(StubBot(), "1", service)

    msg = SimpleNamespace(chat=SimpleNamespace(id=1))
    assert asyncio.run(IDFilter("1")(msg))
    assert not asyncio.run(IDFilter("2")(msg))

    class DummyMessage:
        def __init__(self, text: str) -> None:
            self.text = text
            self.answers: list[tuple[str, dict[str, Any]]] = []

        async def answer(self, text: str, **kwargs: Any) -> None:
            self.answers.append((text, kwargs))

    m_add = DummyMessage("/add foo")
    asyncio.run(bot._cmd_add(m_add))
    assert m_add.answers[0][0] == "Added foo"

    m_add_bad = DummyMessage("/add")
    asyncio.run(bot._cmd_add(m_add_bad))
    assert m_add_bad.answers[0][0].startswith("Usage")

    m_rm = DummyMessage("/remove foo")
    asyncio.run(bot._cmd_remove(m_rm))
    assert m_rm.answers[0][0] == "Removed foo"

    m_rm_bad = DummyMessage("/remove")
    asyncio.run(bot._cmd_remove(m_rm_bad))
    assert m_rm_bad.answers[0][0].startswith("Usage")

    m_list = DummyMessage("/list")
    asyncio.run(bot._cmd_list(m_list))
    text = m_list.answers[0][0]
    assert "List" in text or text == "Watchlist is empty"


@pytest.mark.asyncio
async def test_run_and_stop(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    dispatcher = DummyDispatcher()
    monkeypatch.setattr(
        "twitch_subs.infrastructure.telegram.Dispatcher", lambda: dispatcher
    )
    bot = StubBot()
    service = make_service(tmp_path)
    watch_bot = TelegramWatchlistBot(bot, "1", service)

    async def runner() -> None:
        await asyncio.wait_for(watch_bot.run(), timeout=0.1)

    task = asyncio.create_task(runner())
    await asyncio.sleep(0)
    await watch_bot.stop()
    await task

    assert dispatcher.started and dispatcher.stopped
    assert bot.session.closed
