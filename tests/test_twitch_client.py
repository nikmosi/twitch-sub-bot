from typing import Any

import httpx
import pytest

from twitch_subs.domain.models import BroadcasterType
from twitch_subs.infrastructure.twitch import (
    TWITCH_TOKEN_URL,
    TwitchAuthError,
    TwitchClient,
)


class FakeResp:
    def __init__(self, status_code: int = 200, json_data: dict[str, Any] | None = None):
        self.status_code = status_code
        self._json = json_data or {}

    def json(self) -> dict[str, Any]:
        return self._json

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=httpx.Response(self.status_code))


@pytest.fixture
def token_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch token endpoint to return a valid token."""
    def fake_post(url: str, data: dict[str, Any], timeout: float) -> FakeResp:  # type: ignore[override]
        assert url == TWITCH_TOKEN_URL
        assert data["client_id"] == "cid"
        assert data["client_secret"] == "sec"
        return FakeResp(200, {"access_token": "tok", "expires_in": 3600})

    monkeypatch.setattr(httpx, "post", fake_post)


def make_client(monkeypatch: pytest.MonkeyPatch, get_func: Any, timeout: float = 10.0) -> TwitchClient:
    monkeypatch.setattr(httpx.Client, "get", get_func, raising=False)
    return TwitchClient("cid", "sec", timeout=timeout)


def test_get_user_by_login_ok(monkeypatch: pytest.MonkeyPatch, token_ok: None) -> None:
    def fake_get(self, path: str, params=None, headers=None):  # type: ignore[override]
        assert path == "/helix/users"
        assert params == {"login": "foo"}
        assert headers["Authorization"].startswith("Bearer ")
        return FakeResp(200, {"data": [{"id": "1", "login": "foo", "broadcaster_type": "partner"}]})

    tc = make_client(monkeypatch, fake_get)
    user = tc.get_user_by_login("foo")
    assert user and user.login == "foo"
    assert user.broadcaster_type == BroadcasterType.PARTNER


def test_401_refresh(monkeypatch: pytest.MonkeyPatch) -> None:
    token_calls: list[str] = []

    def fake_post(url: str, data: dict[str, Any], timeout: float) -> FakeResp:  # type: ignore[override]
        token_calls.append("call")
        return FakeResp(200, {"access_token": f"tok{len(token_calls)}", "expires_in": 3600})

    monkeypatch.setattr(httpx, "post", fake_post)

    calls: list[dict[str, str] | None] = []

    def fake_get(self, path: str, params=None, headers=None):  # type: ignore[override]
        calls.append(headers)
        if len(calls) == 1:
            return FakeResp(401)
        return FakeResp(200, {"data": []})

    tc = make_client(monkeypatch, fake_get)
    tc.get_user_by_login("foo")
    assert len(token_calls) == 2
    first, second = calls
    assert first and first["Client-Id"] == "cid"
    assert second and second["Authorization"] == "Bearer tok2"


def test_refresh_before_expiry(monkeypatch: pytest.MonkeyPatch) -> None:
    token_calls = 0

    def fake_post(url: str, data: dict[str, Any], timeout: float) -> FakeResp:  # type: ignore[override]
        nonlocal token_calls
        token_calls += 1
        return FakeResp(200, {"access_token": f"tok{token_calls}", "expires_in": 1})

    monkeypatch.setattr(httpx, "post", fake_post)

    def fake_get(self, path: str, params=None, headers=None):  # type: ignore[override]
        return FakeResp(200, {"data": []})

    tc = make_client(monkeypatch, fake_get)
    tc.get_user_by_login("foo")
    tc.get_user_by_login("bar")
    assert token_calls == 2


def test_5xx_raises(monkeypatch: pytest.MonkeyPatch, token_ok: None) -> None:
    def fake_get(self, path: str, params=None, headers=None):  # type: ignore[override]
        return FakeResp(500)

    tc = make_client(monkeypatch, fake_get)
    with pytest.raises(httpx.HTTPStatusError):
        tc.get_user_by_login("foo")


def test_rate_limit(monkeypatch: pytest.MonkeyPatch, token_ok: None) -> None:
    def fake_get(self, path: str, params=None, headers=None):  # type: ignore[override]
        return FakeResp(429)

    tc = make_client(monkeypatch, fake_get)
    with pytest.raises(httpx.HTTPStatusError):
        tc.get_user_by_login("foo")


def test_timeout(monkeypatch: pytest.MonkeyPatch, token_ok: None) -> None:
    def fake_get(self, path: str, params=None, headers=None):  # type: ignore[override]
        raise httpx.TimeoutException("boom")

    tc = make_client(monkeypatch, fake_get)
    with pytest.raises(httpx.TimeoutException):
        tc.get_user_by_login("foo")


def test_missing_creds() -> None:
    with pytest.raises(TwitchAuthError):
        TwitchClient("", "")
