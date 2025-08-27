from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from twitch_subs import cli
from twitch_subs.infrastructure.repository_sqlite import SqliteWatchlistRepository


def run(command: list[str], monkeypatch: pytest.MonkeyPatch, db: Path):
    runner = CliRunner()
    monkeypatch.setenv("DB_URL", f"sqlite:///{db}")
    monkeypatch.setenv("TWITCH_CLIENT_ID", "id")
    monkeypatch.setenv("TWITCH_CLIENT_SECRET", "secret")
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


def test_add_notifies(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    db = tmp_path / "wl.db"
    messages: list[str] = []
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "c")

    def fake_send(
        self: Any,
        text: str,
        disable_web_page_preview: bool = True,
        disable_notification: bool = False,
    ) -> None:
        _ = self
        _ = disable_web_page_preview
        _ = disable_notification
        messages.append(text)

    monkeypatch.setattr(cli.TelegramNotifier, "send_message", fake_send)
    res = run(["add", "foo"], monkeypatch, db)
    assert res.exit_code == 0
    assert messages == ["➕ <code>foo</code> добавлен в список наблюдения"]


def test_remove_notifies(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    db = tmp_path / "wl.db"
    repo = SqliteWatchlistRepository(f"sqlite:///{db}")
    repo.add("foo")
    messages: list[str] = []
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "c")

    def fake_send(self: Any, text: str, disable_web_page_preview: bool = True) -> None:
        _ = self
        _ = disable_web_page_preview
        messages.append(text)

    monkeypatch.setattr(cli.TelegramNotifier, "send_message", fake_send)
    res = run(["remove", "foo"], monkeypatch, db)
    assert res.exit_code == 0
    assert messages == ["➖ <code>foo</code> удален из списка наблюдения"]
