from __future__ import annotations

import time
from dataclasses import dataclass
from itertools import batched
from typing import Any, Sequence

import httpx
from aiolimiter import AsyncLimiter
from loguru import logger

from twitch_subs.application.ports import TwitchClientProtocol
from twitch_subs.domain.models import BroadcasterType, TwitchAppCreds, UserRecord

TWITCH_API = "https://api.twitch.tv"
TWITCH_TOKEN_URL = "https://id.twitch.tv/oauth2/token"


@dataclass(frozen=True, slots=True)
class TwitchAuthError(RuntimeError):
    """Raised when Twitch credentials are missing."""

    message: str

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.message


class TwitchClient(TwitchClientProtocol):
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        *,
        timeout: float = 20.0,
        async_limiter: AsyncLimiter | None = None,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self._logins_per_request_limit = 100
        if not self.client_id or not self.client_secret:
            raise TwitchAuthError(
                "TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET must be set"
            )
        self._http = httpx.AsyncClient(base_url=TWITCH_API, timeout=timeout)
        self._token: str | None = None
        self._token_exp: float = 0.0
        self._limiter = async_limiter if async_limiter else AsyncLimiter(10, 10)

    @classmethod
    def from_creds(cls, creds: TwitchAppCreds) -> "TwitchClient":
        return cls(creds.client_id, creds.client_secret)

    async def get_users_by_login(
        self, logins: str | Sequence[str]
    ) -> Sequence[UserRecord]:
        if isinstance(logins, str):
            logins = [logins]

        users: list[UserRecord] = []
        for batch in batched(logins, n=self._logins_per_request_limit):
            data = await self._get("/helix/users", params={"login": batch})
            payload_items = data.get("data", [])
            if not payload_items:
                continue

            for user_payload in payload_items:
                broadcaster_type = (
                    user_payload.get("broadcaster_type") or BroadcasterType.NONE.value
                )
                users.append(
                    UserRecord(
                        id=user_payload["id"],
                        login=user_payload["login"],
                        display_name=user_payload.get(
                            "display_name", user_payload["login"]
                        ),
                        broadcaster_type=BroadcasterType(broadcaster_type),
                    )
                )

        return users

    async def _get(
        self, path: str, *, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        await self._ensure_token()
        async with self._limiter:
            response = await self._http.get(
                path, params=params, headers=self._auth_headers()
            )
        if response.status_code == 401:
            logger.warning("Twitch 401: refreshing token and retrying once…")
            await self._refresh_app_token()
            response = await self._http.get(
                path, params=params, headers=self._auth_headers()
            )
        response.raise_for_status()
        return response.json()

    def _auth_headers(self) -> dict[str, str]:
        assert self._token
        return {
            "Client-Id": self.client_id,
            "Authorization": f"Bearer {self._token}",
        }

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""

        await self._http.aclose()

    async def _ensure_token(self) -> None:
        if not self._token or time.time() >= (self._token_exp - 60):
            await self._refresh_app_token()

    async def _refresh_app_token(self) -> None:
        logger.info("Refreshing Twitch app token…")
        response = await self._http.post(
            TWITCH_TOKEN_URL,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "client_credentials",
            },
            timeout=10.0,
        )
        response.raise_for_status()
        data = response.json()
        self._token = data["access_token"]
        self._token_exp = time.time() + int(data.get("expires_in", 0))
