from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import (
    Column,
    CursorResult,
    Index,
    MetaData,
    String,
    Table,
    create_engine,
    delete,
    insert,
    select,
    text,
)
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from twitch_subs.application.ports import SubscriptionStateRepo, WatchlistRepository
from twitch_subs.domain.models import BroadcasterType, SubState

metadata = MetaData()

watchlist = Table(
    "watchlist",
    metadata,
    Column("login", String, primary_key=True),
    Column("created_at", String, nullable=False),
)


subscription_state = Table(
    "subscription_state",
    metadata,
    Column("login", String, primary_key=True),
    Column("broadcaster_type", String, nullable=False),
    Column("since", String),
    Column("updated_at", String, nullable=False),
)
Index("ix_subscription_state_login", subscription_state.c.login)


class SqliteWatchlistRepository(WatchlistRepository):
    """SQLite-backed implementation of :class:`WatchlistRepository`."""

    def __init__(self, engine: Any, echo: bool = False) -> None:
        if isinstance(engine, str):
            self.engine = create_engine(engine, echo=echo, future=True)
            with self.engine.begin() as conn:
                conn.execute(text("PRAGMA journal_mode=WAL"))
            metadata.create_all(self.engine)
        else:
            self.engine = engine

    def add(self, login: str) -> None:
        now = datetime.now(UTC).isoformat()
        with Session(self.engine) as session:
            stmt = insert(watchlist).values(login=login, created_at=now)
            session.execute(stmt.prefix_with("OR IGNORE"))
            session.commit()

    def remove(self, login: str) -> bool:
        with Session(self.engine) as session:
            stmt = delete(watchlist).where(watchlist.c.login == login)
            result = cast(CursorResult[Any], session.execute(stmt))  # pyright: ignore
            session.commit()
            return result.rowcount > 0

    def list(self) -> list[str]:
        with Session(self.engine) as session:
            stmt = select(watchlist.c.login).order_by(watchlist.c.login.asc())
            rows = session.execute(stmt).scalars().all()
            return list(rows)

    def exists(self, login: str) -> bool:
        with Session(self.engine) as session:
            stmt = select(watchlist.c.login).where(watchlist.c.login == login)
            return session.execute(stmt).first() is not None


class SqliteSubscriptionStateRepository(SubscriptionStateRepo):
    """SQLite-backed subscription state repository."""

    def __init__(self, engine: Any, echo: bool = False) -> None:
        if isinstance(engine, str):
            self.engine = create_engine(engine, echo=echo, future=True)
            with self.engine.begin() as conn:
                conn.execute(text("PRAGMA journal_mode=WAL"))
            metadata.create_all(self.engine)
        else:
            self.engine = engine

    def _row_to_state(self, row: Any) -> SubState:
        return SubState(
            login=row["login"],
            broadcaster_type=BroadcasterType(row["broadcaster_type"]),
            since=datetime.fromisoformat(row["since"]) if row["since"] else None,
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def get_sub_state(self, login: str) -> SubState | None:
        with Session(self.engine) as session:
            stmt = select(subscription_state).where(subscription_state.c.login == login)
            row = session.execute(stmt).mappings().first()
            if row is None:
                return None
            return self._row_to_state(row)

    def upsert_sub_state(self, state: SubState) -> None:
        values = {
            "login": state.login,
            "broadcaster_type": state.broadcaster_type.value,
            "since": state.since.isoformat() if state.since else None,
            "updated_at": state.updated_at.isoformat(),
        }
        insert_stmt = sqlite_insert(subscription_state).values(values)
        stmt = insert_stmt.on_conflict_do_update(
            index_elements=[subscription_state.c.login],
            set_={
                "broadcaster_type": insert_stmt.excluded.broadcaster_type,
                "since": insert_stmt.excluded.since,
                "updated_at": insert_stmt.excluded.updated_at,
            },
        )
        with Session(self.engine) as session:
            session.execute(stmt)
            session.commit()

    def set_many(self, states: Iterable[SubState]) -> None:
        values = [
            {
                "login": s.login,
                "broadcaster_type": s.broadcaster_type.value,
                "since": s.since.isoformat() if s.since else None,
                "updated_at": s.updated_at.isoformat(),
            }
            for s in states
        ]
        if not values:
            return
        insert_stmt = sqlite_insert(subscription_state).values(values)
        stmt = insert_stmt.on_conflict_do_update(
            index_elements=[subscription_state.c.login],
            set_={
                "broadcaster_type": insert_stmt.excluded.broadcaster_type,
                "since": insert_stmt.excluded.since,
                "updated_at": insert_stmt.excluded.updated_at,
            },
        )
        with Session(self.engine) as session:
            session.execute(stmt)
            session.commit()

    def list_all(self) -> list[SubState]:
        with Session(self.engine) as session:
            rows = session.execute(select(subscription_state)).mappings().all()
            return [self._row_to_state(row) for row in rows]
