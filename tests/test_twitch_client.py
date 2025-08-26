import os
import time
import httpx
import pytest

from twitch_subs.infrastructure.twitch import TwitchAuthError, TwitchClient


class FakeResp:
    def __init__(self, status_code: int = 200, json_data: dict | None = None):
        self.status_code = status_code
        self._json = json_data or {}

    def json(self) -> dict:
        return self._json

    def raise_for_status(self) -> None:
        if 400 <= self.status_code:
            raise httpx.HTTPStatusError("error", request=None, response=httpx.Response(self.status_code))


def test_missing_env_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TWITCH_CLIENT_ID", raising=False)
    monkeypatch.delenv("TWITCH_CLIENT_SECRET", raising=False)
    with pytest.raises(TwitchAuthError):
        TwitchClient()


def test_headers_and_401_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TWITCH_CLIENT_ID", "cid")
    monkeypatch.setenv("TWITCH_CLIENT_SECRET", "sec")

    token_calls: list[dict] = []

    def fake_post(url: str, data: dict, timeout: float) -> FakeResp:  # type: ignore[override]
        token_calls.append(data)
        return FakeResp(200, {"access_token": f"tok{len(token_calls)}", "expires_in": 3600})

    monkeypatch.setattr(httpx, "post", fake_post)

    calls: list[dict | None] = []

    def fake_get(self, path: str, params=None, headers=None):  # type: ignore[override]
        calls.append(headers)
        if len(calls) == 1:
            return FakeResp(401, {})
        return FakeResp(200, {"data": [{"id": "1", "login": "foo"}]})

    monkeypatch.setattr(httpx.Client, "get", fake_get, raising=False)

    tc = TwitchClient()
    user = tc.get_user_by_login("foo")
    assert user and user.login == "foo"

    assert token_calls and len(token_calls) == 2
    first_headers, second_headers = calls
    assert first_headers and first_headers["Client-Id"] == "cid"
    assert "Authorization" in first_headers
    assert second_headers["Authorization"] == "Bearer tok2"


def test_refresh_before_expiry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TWITCH_CLIENT_ID", "cid")
    monkeypatch.setenv("TWITCH_CLIENT_SECRET", "sec")

    token_calls = 0

    def fake_post(url: str, data: dict, timeout: float) -> FakeResp:  # type: ignore[override]
        nonlocal token_calls
        token_calls += 1
        return FakeResp(200, {"access_token": f"tok{token_calls}", "expires_in": 1})

    monkeypatch.setattr(httpx, "post", fake_post)

    def fake_get(self, path: str, params=None, headers=None):  # type: ignore[override]
        return FakeResp(200, {"data": []})

    monkeypatch.setattr(httpx.Client, "get", fake_get, raising=False)

    tc = TwitchClient()
    tc.get_user_by_login("foo")
    tc.get_user_by_login("bar")
    assert token_calls == 2
