from pathlib import Path

from sqlalchemy import text

from twitch_subs.infrastructure.repository_sqlite import SqliteWatchlistRepository


def test_add_is_idempotent_and_sorted(tmp_path: Path) -> None:
    db = tmp_path / "wl.db"
    repo = SqliteWatchlistRepository(f"sqlite:///{db}")
    repo.add("b")
    repo.add("a")
    repo.add("a")
    assert repo.list() == ["a", "b"]


def test_remove_persistence(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    repo = SqliteWatchlistRepository(f"sqlite:///{db}")
    repo.add("bar")
    assert repo.list() == ["bar"]
    assert repo.remove("bar") is True
    assert repo.remove("bar") is False


def test_add_stores_iso_utc(tmp_path: Path) -> None:
    db = tmp_path / "iso.db"
    repo = SqliteWatchlistRepository(f"sqlite:///{db}")
    repo.add("foo")
    with repo.engine.connect() as conn:
        ts = conn.execute(text("SELECT created_at FROM watchlist")).scalar_one()
    assert ts.endswith("+00:00")
