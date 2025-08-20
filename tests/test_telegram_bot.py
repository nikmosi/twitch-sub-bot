from pathlib import Path

from twitch_subs.infrastructure.telegram import TelegramWatchlistBot
from twitch_subs.infrastructure import watchlist


def test_bot_add_remove_list(tmp_path: Path) -> None:
    path = tmp_path / "watchlist.json"
    bot = TelegramWatchlistBot("token", path)

    assert bot.handle_command("/list") == "Watchlist is empty"

    assert bot.handle_command("/add foo") == "Added foo"
    assert watchlist.load(path) == ["foo"]

    assert "foo" in bot.handle_command("/list")

    assert bot.handle_command("/remove foo") == "Removed foo"
    assert watchlist.load(path) == []
    assert bot.handle_command("/list") == "Watchlist is empty"


def test_bot_duplicate_and_missing(tmp_path: Path) -> None:
    path = tmp_path / "watchlist.json"
    bot = TelegramWatchlistBot("token", path)
    bot.handle_command("/add foo")

    assert bot.handle_command("/add foo") == "foo already present"
    assert bot.handle_command("/remove bar") == "bar not found"
