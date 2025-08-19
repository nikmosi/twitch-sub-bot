from __future__ import annotations

from typing import Protocol

from .models import BroadcasterType, UserRecord


class TwitchClientProtocol(Protocol):
    def get_user_by_login(self, login: str) -> UserRecord | None: ...


class NotifierProtocol(Protocol):
    def send_message(
        self,
        text: str,
        disable_web_page_preview: bool = True,
        disable_notification: bool = False,
    ) -> None: ...


class StateRepositoryProtocol(Protocol):
    def load(self) -> dict[str, BroadcasterType]: ...
    def save(self, state: dict[str, BroadcasterType]) -> None: ...
