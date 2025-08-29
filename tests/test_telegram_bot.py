from pathlib import Path

from twitch_subs.infrastructure.repository_sqlite import SqliteWatchlistRepository
from twitch_subs.infrastructure.telegram import TelegramWatchlistBot


def test_bot_add_remove_list(tmp_path: Path) -> None:
    db = tmp_path / "watch.db"
    repo = SqliteWatchlistRepository(f"sqlite:///{db}")
    bot = TelegramWatchlistBot("123:ABC", "1", repo)

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
    bot = TelegramWatchlistBot("123:ABC", "1", repo)
    bot.handle_command("/add foo")

    assert bot.handle_command("/add foo") == "foo already present"
    assert bot.handle_command("/remove bar") == "bar not found"
