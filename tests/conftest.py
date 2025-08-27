import time
from pathlib import Path
from typing import Callable

import httpx
import pytest

from twitch_subs.infrastructure.repository_sqlite import SqliteWatchlistRepository


@pytest.fixture
def fake_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provide minimal environment variables expected by Settings."""
    monkeypatch.setenv("TWITCH_CLIENT_ID", "cid")
    monkeypatch.setenv("TWITCH_CLIENT_SECRET", "secret")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")


@pytest.fixture
def tmp_db(tmp_path: Path) -> SqliteWatchlistRepository:
    """Return repository bound to a temporary SQLite database."""
    db = tmp_path / "watch.db"
    return SqliteWatchlistRepository(f"sqlite:///{db}")


@pytest.fixture
def httpx_transport() -> Callable[
    [Callable[[httpx.Request], httpx.Response]], httpx.Client
]:
    """Create httpx.Client with a custom MockTransport."""

    def factory(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(handler))

    return factory


@pytest.fixture
def freeze_time(monkeypatch: pytest.MonkeyPatch) -> Callable[[float], None]:
    """Freeze time.time and allow manual advancement."""
    current = 0.0

    def now() -> float:
        return current

    def advance(delta: float) -> None:
        nonlocal current
        current += delta

    monkeypatch.setattr(time, "time", now)
    return advance
