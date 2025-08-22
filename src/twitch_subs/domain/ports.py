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
