import asyncio
import os
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

import twitch_subs.container as container_mod
from twitch_subs import cli
from twitch_subs.config import Settings
from twitch_subs.domain.events import UserAdded, UserRemoved
from twitch_subs.infrastructure.repository_sqlite import SqliteWatchlistRepository
from twitch_subs.infrastructure.telegram import TelegramNotifier


class DummyAiogramBot:
    def __init__(
        self,
        token: str,
        default: Any | None = None,
        session: Any | None = None,
    ) -> None:  # noqa: D401
        self.token = token
        self.default = default
        self.session = session

    async def close(self) -> None:  # noqa: D401
        return None


def run(command: list[str], monkeypatch: pytest.MonkeyPatch, db: Path):
    runner = CliRunner()
    monkeypatch.setenv("DB_URL", f"sqlite:///{db}")
    # Minimal required environment so Settings() does not fail.
    monkeypatch.setenv("TWITCH_CLIENT_ID", "id")
    monkeypatch.setenv("TWITCH_CLIENT_SECRET", "secret")
    if "TELEGRAM_BOT_TOKEN" not in os.environ:
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    if "TELEGRAM_CHAT_ID" not in os.environ:
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "")
    monkeypatch.setattr(container_mod, "Bot", DummyAiogramBot)
    return runner.invoke(cli.app, command)


def test_add_list_remove_happy(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    db = tmp_path / "wl.db"
    res = run(["add", "foo", "-n"], monkeypatch, db)
    assert res.exit_code == 0
    repo = SqliteWatchlistRepository(f"sqlite:///{db}")
    assert repo.list() == ["foo"]
    res = run(["list"], monkeypatch, db)
    assert res.exit_code == 0
    assert res.output.strip() == "foo"
    res = run(["remove", "foo", "-n"], monkeypatch, db)
    assert res.exit_code == 0
    assert (
        run(["list"], monkeypatch, db).output.strip()
        == "Watchlist is empty. Use 'add' to add usernames."
    )


def test_idempotent_add(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    db = tmp_path / "wl.db"
    run(["add", "foo", "-n"], monkeypatch, db)
    run(["add", "foo", "-n"], monkeypatch, db)
    repo = SqliteWatchlistRepository(f"sqlite:///{db}")
    assert repo.list() == ["foo"]


def test_remove_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    db = tmp_path / "wl.db"
    res = run(["remove", "foo", "-n"], monkeypatch, db)
    assert res.exit_code != 0
    assert "not found" in res.output
    res = run(["remove", "foo", "--quiet"], monkeypatch, db)
    assert res.exit_code == 0


def test_username_validation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    db = tmp_path / "wl.db"
    good = run(["add", "user_1", "-n"], monkeypatch, db)
    assert good.exit_code == 0
    bad = run(["add", "bad*name", "-n"], monkeypatch, db)
    assert bad.exit_code == 2


def test_remove_emits_user_removed_event(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    db = tmp_path / "wl.db"
    events: list[object] = []

    class StubEventBus:
        async def publish(self, *published_events: object) -> None:  # noqa: D401
            events.extend(published_events)

    stub_bus = StubEventBus()

    monkeypatch.setattr(cli, "_get_notifier", lambda container: object())
    monkeypatch.setattr(
        container_mod.Container,
        "event_bus",
        property(lambda self: stub_bus),
    )

    add_res = run(["add", "foo"], monkeypatch, db)
    assert add_res.exit_code == 0

    remove_res = run(["remove", "foo"], monkeypatch, db)
    assert remove_res.exit_code == 0

    assert any(isinstance(event, UserAdded) for event in events)
    assert any(isinstance(event, UserRemoved) for event in events)


def test_notify_about_remove_message(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    db = tmp_path / "wl.db"
    messages: list[str] = []

    monkeypatch.setenv("DB_URL", f"sqlite:///{db}")
    monkeypatch.setenv("TWITCH_CLIENT_ID", "id")
    monkeypatch.setenv("TWITCH_CLIENT_SECRET", "secret")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")

    async def capture_send_message(
        self,
        text: str,
        disable_web_page_preview: bool = True,
        disable_notification: bool = False,
    ) -> None:
        messages.append(text)

    monkeypatch.setattr(container_mod, "Bot", DummyAiogramBot)
    monkeypatch.setattr(TelegramNotifier, "send_message", capture_send_message, raising=False)

    container = container_mod.Container(Settings())

    try:
        asyncio.run(container.event_bus.publish(UserRemoved(login="foo")))
    finally:
        asyncio.run(container.aclose())

    assert messages == ["➖ <code>foo</code> удалён из списка наблюдения"]
