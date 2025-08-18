from __future__ import annotations

import httpx
from loguru import logger

from ..domain.models import BroadcasterType, TwitchAppCreds, UserRecord

TWITCH_TOKEN_URL = "https://id.twitch.tv/oauth2/token"
TWITCH_USERS_URL = "https://api.twitch.tv/helix/users"


class TwitchClient:
    def __init__(self, creds: TwitchAppCreds):
        self.creds = creds
        self._token: str | None = None

    def get_app_token(self) -> str:
        if self._token is None:
            data = {
                "client_id": self.creds.client_id,
                "client_secret": self.creds.client_secret,
                "grant_type": "client_credentials",
            }
            with httpx.Client(timeout=20.0) as c:
                r = c.post(TWITCH_TOKEN_URL, data=data)
                r.raise_for_status()
                self._token = r.json()["access_token"]
        return self._token

    def get_user_by_login(self, login: str) -> UserRecord | None:
        token = self.get_app_token()
        headers = {"Client-Id": self.creds.client_id, "Authorization": f"Bearer {token}"}
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
