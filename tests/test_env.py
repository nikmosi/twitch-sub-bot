import pytest

from twitch_subs.infrastructure import env


def test_get_db_url_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DB_URL", raising=False)
    assert env.get_db_url() == "sqlite:///./data.db"


def test_get_db_url_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DB_URL", "sqlite:///x.db")
    assert env.get_db_url() == "sqlite:///x.db"


@pytest.mark.parametrize(
    "value, expected",
    [
        ("1", True),
        ("true", True),
        ("yes", True),
        ("0", False),
        ("no", False),
        ("", False),
    ],
)
def test_get_db_echo(monkeypatch: pytest.MonkeyPatch, value: str, expected: bool) -> None:
    monkeypatch.setenv("DB_ECHO", value)
    assert env.get_db_echo() is expected
