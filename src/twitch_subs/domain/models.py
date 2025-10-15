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
class LoginReportInfo:
    login: str
    status: str


@dataclass(frozen=True, slots=True)
class SubState:
    login: str
    is_subscribed: bool
    tier: str | None = None
    since: datetime | None = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


