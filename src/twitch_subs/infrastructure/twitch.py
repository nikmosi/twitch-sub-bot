from __future__ import annotations

import time
from typing import Any

import httpx
from aiolimiter import AsyncLimiter
from loguru import logger

from twitch_subs.application.ports import TwitchClientProtocol
from twitch_subs.domain.models import BroadcasterType, TwitchAppCreds, UserRecord

TWITCH_API = "https://api.twitch.tv"
TWITCH_TOKEN_URL = "https://id.twitch.tv/oauth2/token"


class TwitchAuthError(RuntimeError):
    """Raised when Twitch credentials are missing."""


class TwitchClient(TwitchClientProtocol):
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        *,
        timeout: float = 10.0,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        if not self.client_id or not self.client_secret:
            raise TwitchAuthError(
                "TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET must be set"
            )
        self._http = httpx.Client(base_url=TWITCH_API, timeout=timeout)
        self._token: str | None = None
        self._token_exp: float = 0.0
        self._limiter = AsyncLimiter(10, 10)

    @classmethod
    def from_creds(cls, creds: TwitchAppCreds) -> "TwitchClient":
        return cls(creds.client_id, creds.client_secret)

    async def get_user_by_login(self, login: str) -> UserRecord | None:
        data = await self._get("/helix/users", params={"login": login})
        items = data.get("data", [])
        if not items:
            return None
        u = items[0]
        btype = u.get("broadcaster_type") or BroadcasterType.NONE.value
        return UserRecord(
            id=u["id"],
            login=u["login"],
            display_name=u.get("display_name", u["login"]),
            broadcaster_type=BroadcasterType(btype),
        )

    async def _get(
        self, path: str, *, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        self._ensure_token()
        async with self._limiter:
            r = self._http.get(path, params=params, headers=self._auth_headers())
        if r.status_code == 401:
            logger.warning("Twitch 401: refreshing token and retrying once…")
            self._refresh_app_token()
            r = self._http.get(path, params=params, headers=self._auth_headers())
        r.raise_for_status()
        return r.json()

    def _auth_headers(self) -> dict[str, str]:
        assert self._token
        return {
            "Client-Id": self.client_id,
            "Authorization": f"Bearer {self._token}",
        }

    def _ensure_token(self) -> None:
        if not self._token or time.time() >= (self._token_exp - 60):
            self._refresh_app_token()

    def _refresh_app_token(self) -> None:
        logger.info("Refreshing Twitch app token…")
        r = httpx.post(
            TWITCH_TOKEN_URL,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "client_credentials",
            },
            timeout=10.0,
        )
        r.raise_for_status()
        data = r.json()
        self._token = data["access_token"]
        self._token_exp = time.time() + int(data.get("expires_in", 0))
