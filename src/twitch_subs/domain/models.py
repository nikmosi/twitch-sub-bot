from __future__ import annotations

from collections.abc import Iterator, MutableMapping
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
    login: str
    is_subscribed: bool
    tier: str | None = None
    since: datetime | None = None
    updated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


@dataclass
class State(MutableMapping[str, BroadcasterType]):
    """Mapping of login names to their last known broadcaster type."""

    logins: dict[str, BroadcasterType] = field(
        default_factory=dict[str, BroadcasterType]
    )

    def __getitem__(self, key: str) -> BroadcasterType:
        return self.logins[key]

    def __setitem__(self, key: str, value: BroadcasterType) -> None:
        self.logins[key] = value

    def __delitem__(self, key: str) -> None:
        del self.logins[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.logins)

    def __len__(self) -> int:
        return len(self.logins)

    def copy(self) -> "State":
        return State(self.logins.copy())
