from pathlib import Path

from twitch_subs.infrastructure.repository_sqlite import SqliteWatchlistRepository


def test_add_list_exists_in_memory() -> None:
    repo = SqliteWatchlistRepository("sqlite:///:memory:")
    repo.add("foo")
    repo.add("foo")
    assert repo.exists("foo") is True
    assert repo.list() == ["foo"]


def test_remove_persistence(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    repo = SqliteWatchlistRepository(f"sqlite:///{db}")
    repo.add("bar")
    assert repo.list() == ["bar"]
    assert repo.remove("bar") is True
    assert repo.remove("bar") is False
