from pathlib import Path
from datetime import datetime, timezone

from sqlalchemy import text

from twitch_subs.domain.models import BroadcasterType, SubState
from twitch_subs.infrastructure.repository_sqlite import (
    SqliteSubscriptionStateRepository,
    SqliteWatchlistRepository,
)


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


def test_exists(tmp_path: Path) -> None:
    db = tmp_path / "exists.db"
    repo = SqliteWatchlistRepository(f"sqlite:///{db}")
    repo.add("foo")
    assert repo.exists("foo")
    assert not repo.exists("bar")


def test_subscription_state_crud(tmp_path: Path) -> None:
    db = tmp_path / "sub.db"
    repo = SqliteSubscriptionStateRepository(f"sqlite:///{db}")
    st = SubState(
        "foo",
        BroadcasterType.AFFILIATE,
        since=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    repo.upsert_sub_state(st)
    loaded = repo.get_sub_state("foo")
    assert loaded is not None and loaded.is_subscribed
    st2 = SubState("foo", BroadcasterType.NONE)
    repo.upsert_sub_state(st2)
    loaded2 = repo.get_sub_state("foo")
    assert loaded2 is not None and not loaded2.is_subscribed


def test_subscription_state_set_many(tmp_path: Path) -> None:
    db = tmp_path / "many.db"
    repo = SqliteSubscriptionStateRepository(f"sqlite:///{db}")
    repo.set_many(
        [
            SubState("a", BroadcasterType.PARTNER),
            SubState("b", BroadcasterType.NONE),
        ]
    )
    rows = repo.list_all()
    assert {r.login for r in rows} == {"a", "b"}


def test_subscription_state_iso(tmp_path: Path) -> None:
    db = tmp_path / "iso.db"
    repo = SqliteSubscriptionStateRepository(f"sqlite:///{db}")
    repo.upsert_sub_state(SubState("foo", BroadcasterType.AFFILIATE))
    with repo.engine.connect() as conn:
        ts = conn.execute(
            text("SELECT updated_at FROM subscription_state")
        ).scalar_one()
    assert ts.endswith("+00:00")
