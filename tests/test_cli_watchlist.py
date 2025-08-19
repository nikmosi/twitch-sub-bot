from pathlib import Path

import json
from typer.testing import CliRunner

from twitch_subs import cli
from twitch_subs.infrastructure import watchlist


def run(command: list[str], monkeypatch, path: Path):
    runner = CliRunner()
    monkeypatch.setenv("TWITCH_SUBS_WATCHLIST", str(path))
    return runner.invoke(cli.app, command)


def test_add_list_remove_happy(monkeypatch, tmp_path):
    path = tmp_path / "wl.json"
    res = run(["add", "foo"], monkeypatch, path)
    assert res.exit_code == 0
    assert path.exists()
    res = run(["list"], monkeypatch, path)
    assert res.exit_code == 0
    assert res.output.strip() == "foo"
    res = run(["remove", "foo"], monkeypatch, path)
    assert res.exit_code == 0
    assert run(["list"], monkeypatch, path).output.strip() == "Watchlist is empty. Use 'add' to add usernames."


def test_idempotent_add(monkeypatch, tmp_path):
    path = tmp_path / "wl.json"
    run(["add", "foo"], monkeypatch, path)
    run(["add", "foo"], monkeypatch, path)
    data = json.loads(path.read_text())
    assert data["users"] == ["foo"]


def test_remove_missing(monkeypatch, tmp_path):
    path = tmp_path / "wl.json"
    res = run(["remove", "foo"], monkeypatch, path)
    assert res.exit_code != 0
    assert "not found" in res.output
    res = run(["remove", "foo", "--quiet"], monkeypatch, path)
    assert res.exit_code == 0


def test_custom_watchlist_option(monkeypatch, tmp_path):
    path = tmp_path / "custom.json"
    runner = CliRunner()
    res = runner.invoke(cli.app, ["add", "foo", "--watchlist", str(path)])
    assert res.exit_code == 0
    assert json.loads(path.read_text())["users"] == ["foo"]


def test_username_validation(monkeypatch, tmp_path):
    path = tmp_path / "wl.json"
    good = run(["add", "user_1"], monkeypatch, path)
    assert good.exit_code == 0
    bad = run(["add", "bad*name"], monkeypatch, path)
    assert bad.exit_code == 2


def test_atomic_write(monkeypatch, tmp_path):
    path = tmp_path / "wl.json"
    res = run(["add", "foo"], monkeypatch, path)
    assert res.exit_code == 0
    tmp_file = path.with_suffix(path.suffix + ".tmp")
    assert not tmp_file.exists()
    assert json.loads(path.read_text())["users"] == ["foo"]


def test_default_watchlist_path(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    path = watchlist.resolve_path(env={})
    assert path == Path(".watchlist.json")
    assert path.resolve() == tmp_path / ".watchlist.json"
