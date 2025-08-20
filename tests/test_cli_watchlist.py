import json
from pathlib import Path
from typing import Any

from pytest import MonkeyPatch
from typer.testing import CliRunner

from twitch_subs import cli
from twitch_subs.infrastructure import watchlist


def run(command: list[str], monkeypatch: MonkeyPatch, path: Path):
    runner = CliRunner()
    monkeypatch.setenv("TWITCH_SUBS_WATCHLIST", str(path))
    return runner.invoke(cli.app, command)


def test_add_list_remove_happy(monkeypatch: MonkeyPatch, tmp_path: Path):
    path = tmp_path / "wl.json"
    res = run(["add", "foo"], monkeypatch, path)
    assert res.exit_code == 0
    assert path.exists()
    res = run(["list"], monkeypatch, path)
    assert res.exit_code == 0
    assert res.output.strip() == "foo"
    res = run(["remove", "foo"], monkeypatch, path)
    assert res.exit_code == 0
    assert (
        run(["list"], monkeypatch, path).output.strip()
        == "Watchlist is empty. Use 'add' to add usernames."
    )


def test_idempotent_add(monkeypatch: MonkeyPatch, tmp_path: Path):
    path = tmp_path / "wl.json"
    run(["add", "foo"], monkeypatch, path)
    run(["add", "foo"], monkeypatch, path)
    data = json.loads(path.read_text())
    assert data["users"] == ["foo"]


def test_remove_missing(monkeypatch: MonkeyPatch, tmp_path: Path):
    path = tmp_path / "wl.json"
    res = run(["remove", "foo"], monkeypatch, path)
    assert res.exit_code != 0
    assert "not found" in res.output
    res = run(["remove", "foo", "--quiet"], monkeypatch, path)
    assert res.exit_code == 0


def test_custom_watchlist_option(tmp_path: Path):
    path = tmp_path / "custom.json"
    runner = CliRunner()
    res = runner.invoke(cli.app, ["add", "foo", "--watchlist", str(path)])
    assert res.exit_code == 0
    assert json.loads(path.read_text())["users"] == ["foo"]


def test_username_validation(monkeypatch: MonkeyPatch, tmp_path: Path):
    path = tmp_path / "wl.json"
    good = run(["add", "user_1"], monkeypatch, path)
    assert good.exit_code == 0
    bad = run(["add", "bad*name"], monkeypatch, path)
    assert bad.exit_code == 2


def test_atomic_write(monkeypatch: MonkeyPatch, tmp_path: Path):
    path = tmp_path / "wl.json"
    res = run(["add", "foo"], monkeypatch, path)
    assert res.exit_code == 0
    tmp_file = path.with_suffix(path.suffix + ".tmp")
    assert not tmp_file.exists()
    assert json.loads(path.read_text())["users"] == ["foo"]


def test_default_watchlist_path(monkeypatch: MonkeyPatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    path = watchlist.resolve_path(env={})
    assert path == Path(".watchlist.json")
    assert path.resolve() == tmp_path / ".watchlist.json"


def test_add_notifies(monkeypatch: MonkeyPatch, tmp_path: Path):
    path = tmp_path / "wl.json"
    messages: list[str] = []
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "c")
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)

    def fake_send(self: Any, text: str, disable_web_page_preview: bool = True) -> None:
        _ = self
        _ = disable_web_page_preview
        messages.append(text)

    monkeypatch.setattr(cli.TelegramNotifier, "send_message", fake_send)
    res = run(["add", "foo"], monkeypatch, path)
    assert res.exit_code == 0
    assert messages == ["➕ <code>foo</code> добавлен в список наблюдения"]


def test_remove_notifies(monkeypatch: MonkeyPatch, tmp_path: Path):
    path = tmp_path / "wl.json"
    watchlist.save(path, ["foo"])
    messages: list[str] = []
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "c")
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)

    def fake_send(self: Any, text: str, disable_web_page_preview: bool = True) -> None:
        _ = self
        _ = disable_web_page_preview
        messages.append(text)

    monkeypatch.setattr(cli.TelegramNotifier, "send_message", fake_send)
    res = run(["remove", "foo"], monkeypatch, path)
    assert res.exit_code == 0
    assert messages == ["➖ <code>foo</code> удален из списка наблюдения"]
