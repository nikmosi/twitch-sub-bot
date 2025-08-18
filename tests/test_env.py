import pytest

from twitch_subs.infrastructure.env import require_env


def test_require_env_returns_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FOO", "bar")
    assert require_env("FOO") == "bar"


@pytest.mark.parametrize("value,action", [("", "set"), (None, "del")])
def test_require_env_missing(monkeypatch: pytest.MonkeyPatch, value: str | None, action: str) -> None:
    if action == "set":
        monkeypatch.setenv("FOO", value or "")
    else:
        monkeypatch.delenv("FOO", raising=False)
    with pytest.raises(RuntimeError):
        require_env("FOO")
