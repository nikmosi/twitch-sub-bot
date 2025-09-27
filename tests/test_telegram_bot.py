import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from twitch_subs.application.watchlist_service import WatchlistService
from twitch_subs.infrastructure.repository_sqlite import SqliteWatchlistRepository
from twitch_subs.infrastructure.telegram import IDFilter, TelegramWatchlistBot


class DummyBot:
    async def session_close(self) -> None:  # pragma: no cover - compatibility helper
        pass


def test_bot_add_remove_list(tmp_path: Path) -> None:
    db = tmp_path / "watch.db"
    repo = SqliteWatchlistRepository(f"sqlite:///{db}")
    service = WatchlistService(repo)
    bot = TelegramWatchlistBot(DummyBot(), "1", service)

    assert bot.handle_command("/list") == "Watchlist is empty"

    assert bot.handle_command("/add foo") == "Added foo"
    assert repo.list() == ["foo"]

    assert "foo" in bot.handle_command("/list")

    assert bot.handle_command("/remove foo") == "Removed foo"
    assert repo.list() == []
    assert bot.handle_command("/list") == "Watchlist is empty"


def test_bot_duplicate_and_missing(tmp_path: Path) -> None:
    db = tmp_path / "watch.db"
    repo = SqliteWatchlistRepository(f"sqlite:///{db}")
    service = WatchlistService(repo)
    bot = TelegramWatchlistBot(DummyBot(), "1", service)
    bot.handle_command("/add foo")

    assert bot.handle_command("/add foo") == "foo already present"
    assert bot.handle_command("/remove bar") == "bar not found"


def test_handle_command_unknown(tmp_path: Path) -> None:
    repo = SqliteWatchlistRepository(f"sqlite:///{tmp_path / 'db.sqlite'}")
    bot = TelegramWatchlistBot(DummyBot(), "1", WatchlistService(repo))
    assert bot.handle_command("/foo") == "Unknown command"


def test_id_filter_and_handlers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    db = tmp_path / "watch.db"
    service = WatchlistService(SqliteWatchlistRepository(f"sqlite:///{db}"))
    bot = TelegramWatchlistBot(DummyBot(), "1", service)

    msg = SimpleNamespace(chat=SimpleNamespace(id=1))
    assert asyncio.run(IDFilter("1")(msg))
    assert not asyncio.run(IDFilter("2")(msg))

    class DummyMessage:
        def __init__(self, text: str):
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
    assert (
        m_list.answers
        and "List" in m_list.answers[0][0]
        or m_list.answers[0][0] == "Watchlist is empty"
    )
