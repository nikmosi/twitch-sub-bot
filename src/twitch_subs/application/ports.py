from __future__ import annotations

from collections.abc import Iterable
from typing import Awaitable, Callable, Protocol, Sequence, TypeVar

from twitch_subs.domain.events import DomainEvent
from twitch_subs.domain.models import (
    BroadcasterType,
    LoginStatus,
    SubState,
    UserRecord,
)

E = TypeVar("E", bound=DomainEvent)

Handler = Callable[[E], Awaitable[None]]


class EventBus(Protocol):
    async def publish(self, *events: DomainEvent) -> None: ...
    def subscribe(self, event_type: type[DomainEvent], handler: Handler[E]) -> None: ...


class TwitchClientProtocol(Protocol):
    async def get_user_by_login(
        self, login: str
    ) -> UserRecord | None: ...  # pragma: no cover


class NotifierProtocol(Protocol):
    async def notify_about_change(
        self, status: LoginStatus, curr: BroadcasterType
    ) -> None: ...  # pragma: no cover

    async def notify_about_start(self) -> None: ...  # pragma: no cover
    async def notify_about_stop(self) -> None: ...  # pragma: no cover

    async def notify_report(
        self,
        states: Sequence[SubState],
        checks: int,
        errors: int,
    ) -> None: ...  # pragma: no cover

    async def send_message(
        self,
        text: str,
        disable_web_page_preview: bool = True,
        disable_notification: bool = False,
    ) -> None: ...  # pragma: no cover


class WatchlistRepository(Protocol):
    """Persistence abstraction for the watchlist of Twitch logins."""

    def add(self, login: str) -> None:
        """Add *login* to the watchlist. Idempotent."""
        ...  # pragma: no cover

    def remove(self, login: str) -> bool:
        """Remove *login* from the watchlist.

        Returns ``True`` if the login was present and removed.
        """
        ...  # pragma: no cover

    def list(self) -> list[str]:
        """Return all logins from the watchlist sorted alphabetically."""
        ...  # pragma: no cover

    def exists(self, login: str) -> bool:
        """Return ``True`` if *login* is already in the watchlist."""
        ...  # pragma: no cover


class SubscriptionStateRepo(Protocol):
    def get_sub_state(self, login: str) -> SubState | None: ...  # pragma: no cover

    def upsert_sub_state(self, state: SubState) -> None: ...  # pragma: no cover

    def set_many(self, states: Iterable[SubState]) -> None: ...  # pragma: no cover
