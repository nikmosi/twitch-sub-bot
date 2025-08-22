from __future__ import annotations

from twitch_subs.domain.ports import WatchlistRepository

from .env import get_db_echo, get_db_url
from .repository_sqlite import SqliteWatchlistRepository


def build_watchlist_repo() -> WatchlistRepository:
    """Construct a :class:`SqliteWatchlistRepository` using environment settings."""

    return SqliteWatchlistRepository(get_db_url(), get_db_echo())


__all__ = ["build_watchlist_repo", "SqliteWatchlistRepository"]
