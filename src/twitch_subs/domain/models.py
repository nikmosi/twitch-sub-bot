from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class BroadcasterType(str, Enum):
    NONE = "none"
    AFFILIATE = "affiliate"
    PARTNER = "partner"

    def is_subscribable(self) -> bool:
        return self in {BroadcasterType.AFFILIATE, BroadcasterType.PARTNER}


@dataclass(frozen=True)
class TwitchAppCreds:
    client_id: str
    client_secret: str


@dataclass(frozen=True)
class UserRecord:
    id: str
    login: str
    display_name: str
    broadcaster_type: BroadcasterType


@dataclass(frozen=True)
class LoginStatus:
    """Result of a single login check."""

    login: str
    broadcaster_type: BroadcasterType
    user: UserRecord | None


@dataclass(frozen=True, slots=True)
class SubState:
    """Last known subscription state for a Twitch login."""

    login: str
    broadcaster_type: BroadcasterType
    since: datetime | None = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_subscribed(self) -> bool:
        return self.broadcaster_type.is_subscribable()

    @classmethod
    def unsubscribed(
        cls, login: str, *, updated_at: datetime | None = None
    ) -> "SubState":
        """Factory for unsubscribed state with predictable timestamps."""

        return cls(
            login=login,
            broadcaster_type=BroadcasterType.NONE,
            since=None,
            updated_at=updated_at or datetime.now(timezone.utc),
        )
