from __future__ import annotations

from typing import Self

import httpx

from ..domain.models import BroadcasterType, TwitchAppCreds, UserRecord

TWITCH_TOKEN_URL = "https://id.twitch.tv/oauth2/token"
TWITCH_USERS_URL = "https://api.twitch.tv/helix/users"


class TwitchClient:
    def __init__(self, token: str, cliend_id: str):
        self._token: str = token
        self._client_id = cliend_id

    @classmethod
    def from_creds(cls, creds: TwitchAppCreds) -> Self:
        data = {
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "grant_type": "client_credentials",
        }
        with httpx.Client(timeout=20.0) as c:
            r = c.post(TWITCH_TOKEN_URL, data=data)
            r.raise_for_status()
            token = r.json()["access_token"]
        return cls(token, creds.client_id)

    def get_user_by_login(self, login: str) -> UserRecord | None:
        headers = {
            "Client-Id": self._client_id,
            "Authorization": f"Bearer {self._token}",
        }
        params = {"login": login}
        with httpx.Client(timeout=15.0) as c:
            r = c.get(TWITCH_USERS_URL, headers=headers, params=params)
            r.raise_for_status()
            data = r.json().get("data", [])
            if not data:
                return None
            u = data[0]
            return UserRecord(
                id=u["id"],
                login=u["login"],
                display_name=u.get("display_name", u["login"]),
                broadcaster_type=BroadcasterType(u.get("broadcaster_type", "")),
            )
