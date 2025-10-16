from typing import Any

import httpx
import pytest

from twitch_subs.domain.models import BroadcasterType, TwitchAppCreds
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
            raise httpx.HTTPStatusError(
                "error",
                request=None,  # pyright: ignore[reportArgumentType]
                response=httpx.Response(self.status_code),
            )


@pytest.fixture
def token_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch token endpoint to return a valid token."""

    async def fake_post(
        self,
        url: str,
        *,
        data: dict[str, Any] | None = None,
        timeout: float | None = None,
        **_: Any,
    ) -> FakeResp:  # type: ignore[override]
        assert url == TWITCH_TOKEN_URL
        assert data is not None
        assert data["client_id"] == "cid"
        assert data["client_secret"] == "sec"
        return FakeResp(200, {"access_token": "tok", "expires_in": 3600})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post, raising=False)


def make_client(
    monkeypatch: pytest.MonkeyPatch, get_func: Any, timeout: float = 10.0
) -> TwitchClient:
    monkeypatch.setattr(httpx.AsyncClient, "get", get_func, raising=False)
    return TwitchClient("cid", "sec", timeout=timeout)


@pytest.mark.asyncio
async def test_get_user_by_login_ok(
    monkeypatch: pytest.MonkeyPatch, token_ok: None
) -> None:
    async def fake_get(
        self,
        path: str,
        *,
        params: Any = None,
        headers: dict[str, str],
        **_: Any,
    ) -> FakeResp:  # type: ignore[override]
        assert path == "/helix/users"
        assert params == {"login": "foo"}
        assert headers["Authorization"].startswith("Bearer ")
        return FakeResp(
            200, {"data": [{"id": "1", "login": "foo", "broadcaster_type": "partner"}]}
        )

    tc = make_client(monkeypatch, fake_get)
    try:
        user = await tc.get_user_by_login("foo")
        assert user and user.login == "foo"
        assert user.broadcaster_type == BroadcasterType.PARTNER
    finally:
        await tc.aclose()


@pytest.mark.asyncio
async def test_401_refresh(monkeypatch: pytest.MonkeyPatch) -> None:
    token_calls: list[str] = []

    async def fake_post(
        self,
        url: str,
        *,
        data: dict[str, Any] | None = None,
        timeout: float | None = None,
        **_: Any,
    ) -> FakeResp:  # type: ignore[override]
        token_calls.append("call")
        return FakeResp(
            200, {"access_token": f"tok{len(token_calls)}", "expires_in": 3600}
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post, raising=False)

    calls: list[dict[str, str] | None] = []

    async def fake_get(
        self,
        path: str,
        *,
        params: Any = None,
        headers: Any,
        **_: Any,
    ) -> FakeResp:  # type: ignore[override]
        calls.append(headers)
        if len(calls) == 1:
            return FakeResp(401)
        return FakeResp(200, {"data": []})

    tc = make_client(monkeypatch, fake_get)
    try:
        await tc.get_user_by_login("foo")
        assert len(token_calls) == 2
        first, second = calls
        assert first and first["Client-Id"] == "cid"
        assert second and second["Authorization"] == "Bearer tok2"
    finally:
        await tc.aclose()


@pytest.mark.asyncio
async def test_refresh_before_expiry(monkeypatch: pytest.MonkeyPatch) -> None:
    token_calls = 0

    async def fake_post(
        self,
        url: str,
        *,
        data: dict[str, Any] | None = None,
        timeout: float | None = None,
        **_: Any,
    ) -> FakeResp:  # type: ignore[override]
        nonlocal token_calls
        token_calls += 1
        return FakeResp(200, {"access_token": f"tok{token_calls}", "expires_in": 1})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post, raising=False)

    async def fake_get(
        self,
        path: str,
        *,
        params: Any = None,
        headers: Any = None,
        **_: Any,
    ) -> FakeResp:  # type: ignore[override]
        return FakeResp(200, {"data": []})

    tc = make_client(monkeypatch, fake_get)
    try:
        await tc.get_user_by_login("foo")
        await tc.get_user_by_login("bar")
        assert token_calls == 2
    finally:
        await tc.aclose()


@pytest.mark.asyncio
async def test_5xx_raises(
    monkeypatch: pytest.MonkeyPatch, token_ok: None
) -> None:
    async def fake_get(
        self,
        path: str,
        *,
        params: Any = None,
        headers: Any = None,
        **_: Any,
    ) -> FakeResp:  # type: ignore[override]
        return FakeResp(500)

    tc = make_client(monkeypatch, fake_get)
    try:
        with pytest.raises(httpx.HTTPStatusError):
            await tc.get_user_by_login("foo")
    finally:
        await tc.aclose()


@pytest.mark.asyncio
async def test_rate_limit(
    monkeypatch: pytest.MonkeyPatch, token_ok: None
) -> None:
    async def fake_get(
        self,
        path: str,
        *,
        params: Any = None,
        headers: Any = None,
        **_: Any,
    ) -> FakeResp:  # type: ignore[override]
        return FakeResp(429)

    tc = make_client(monkeypatch, fake_get)
    try:
        with pytest.raises(httpx.HTTPStatusError):
            await tc.get_user_by_login("foo")
    finally:
        await tc.aclose()


@pytest.mark.asyncio
async def test_timeout(monkeypatch: pytest.MonkeyPatch, token_ok: None) -> None:
    async def fake_get(
        self,
        path: str,
        *,
        params: Any = None,
        headers: Any = None,
        **_: Any,
    ) -> FakeResp:  # type: ignore[override]
        raise httpx.TimeoutException("boom")

    tc = make_client(monkeypatch, fake_get)
    try:
        with pytest.raises(httpx.TimeoutException):
            await tc.get_user_by_login("foo")
    finally:
        await tc.aclose()


def test_missing_creds() -> None:
    with pytest.raises(TwitchAuthError):
        TwitchClient("", "")


def test_from_creds() -> None:
    creds = TwitchAppCreds("cid", "sec")
    client = TwitchClient.from_creds(creds)
    assert isinstance(client, TwitchClient)


@pytest.mark.asyncio
async def test_get_user_none(
    monkeypatch: pytest.MonkeyPatch, token_ok: None
) -> None:
    async def fake_get(
        self,
        path: str,
        *,
        params: Any = None,
        headers: Any = None,
        **_: Any,
    ) -> FakeResp:  # type: ignore[override]
        return FakeResp(200, {"data": []})

    tc = make_client(monkeypatch, fake_get)
    try:
        assert await tc.get_user_by_login("foo") is None
    finally:
        await tc.aclose()


@pytest.mark.asyncio
async def test_aclose_closes_http_client(monkeypatch: pytest.MonkeyPatch) -> None:
    closed = False

    async def fake_aclose(self) -> None:  # type: ignore[override]
        nonlocal closed
        closed = True

    monkeypatch.setattr(httpx.AsyncClient, "aclose", fake_aclose, raising=False)

    client = TwitchClient("cid", "sec")
    await client.aclose()
    assert closed
