import os
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

import twitch_subs.container as container_mod
from twitch_subs import cli
from twitch_subs.infrastructure.repository_sqlite import SqliteWatchlistRepository


class DummyAiogramBot:
    def __init__(
        self,
        token: str,
        session: Any | None = None,
        default: Any | None = None,
    ) -> None:  # noqa: D401
        self.token = token
        self.session = session
        self.default = default

    async def close(self) -> None:  # noqa: D401
        pass


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
