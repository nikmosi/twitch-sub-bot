from __future__ import annotations

from datetime import datetime
from typing import List

from sqlalchemy import Column, MetaData, String, Table, create_engine, select, text, insert, delete
from sqlalchemy.orm import Session

from ..domain.ports import WatchlistRepository

metadata = MetaData()

watchlist = Table(
    "watchlist",
    metadata,
    Column("login", String, primary_key=True),
    Column("created_at", String, nullable=False),
)


class SqliteWatchlistRepository(WatchlistRepository):
    """SQLite-backed implementation of :class:`WatchlistRepository`."""

    def __init__(self, db_url: str, echo: bool = False) -> None:
        self.engine = create_engine(db_url, echo=echo, future=True)
        with self.engine.begin() as conn:
            conn.execute(text("PRAGMA journal_mode=WAL"))
        metadata.create_all(self.engine)

    def add(self, login: str) -> None:
        now = datetime.utcnow().isoformat()
        with Session(self.engine) as session:
            stmt = insert(watchlist).values(login=login, created_at=now)
            session.execute(stmt.prefix_with("OR IGNORE"))
            session.commit()

    def remove(self, login: str) -> bool:
        with Session(self.engine) as session:
            stmt = delete(watchlist).where(watchlist.c.login == login)
            result = session.execute(stmt)
            session.commit()
            return result.rowcount > 0

    def list(self) -> List[str]:
        with Session(self.engine) as session:
            stmt = select(watchlist.c.login).order_by(watchlist.c.login.asc())
            rows = session.execute(stmt).scalars().all()
            return list(rows)

    def exists(self, login: str) -> bool:
        with Session(self.engine) as session:
            stmt = select(watchlist.c.login).where(watchlist.c.login == login)
            return session.execute(stmt).first() is not None
