from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, Sequence

from .models import BroadcasterType, LoginStatus, SubState, UserRecord


class TwitchClientProtocol(Protocol):
    async def get_user_by_login(self, login: str) -> UserRecord | None: ...


class NotifierProtocol(Protocol):
    def notify_about_change(
        self, status: LoginStatus, curr: BroadcasterType
    ) -> None: ...

    def notify_about_start(self) -> None: ...

    def notify_report(
        self,
        logins: Sequence[str],
        state: dict[str, BroadcasterType],
        checks: int,
        errors: int,
    ) -> None: ...

    def send_message(
        self,
        text: str,
        disable_web_page_preview: bool = True,
        disable_notification: bool = False,
    ) -> None: ...


class WatchlistRepository(Protocol):
    """Persistence abstraction for the watchlist of Twitch logins."""

    def add(self, login: str) -> None:
        """Add *login* to the watchlist. Idempotent."""
        ...

    def remove(self, login: str) -> bool:
        """Remove *login* from the watchlist.

        Returns ``True`` if the login was present and removed.
        """
        ...

    def list(self) -> list[str]:
        """Return all logins from the watchlist sorted alphabetically."""
        ...

    def exists(self, login: str) -> bool:
        """Return ``True`` if *login* is already in the watchlist."""
        ...


class SubscriptionStateRepo(Protocol):
    def get_sub_state(self, login: str) -> SubState | None: ...

    def upsert_sub_state(self, state: SubState) -> None: ...

    def set_many(self, states: Iterable[SubState]) -> None: ...
