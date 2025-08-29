from __future__ import annotations

from twitch_subs.domain.ports import WatchlistRepository

from ..config import Settings
from .repository_sqlite import SqliteWatchlistRepository


def build_watchlist_repo(settings: Settings) -> WatchlistRepository:
    """Construct a :class:`SqliteWatchlistRepository` using *settings*."""

    return SqliteWatchlistRepository(settings.database_url, settings.database_echo)


__all__ = ["build_watchlist_repo", "SqliteWatchlistRepository"]
