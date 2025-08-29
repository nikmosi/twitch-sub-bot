from pathlib import Path

from twitch_subs.application.watchlist_service import WatchlistService
from twitch_subs.infrastructure.repository_sqlite import SqliteWatchlistRepository


def test_watchlist_service_crud(tmp_path: Path) -> None:
    db = tmp_path / "watch.db"
    repo = SqliteWatchlistRepository(f"sqlite:///{db}")
    service = WatchlistService(repo)

    assert service.list() == []
    assert service.add("foo") is True
    assert service.add("foo") is False
    assert service.list() == ["foo"]
    assert service.remove("foo") is True
    assert service.remove("foo") is False
