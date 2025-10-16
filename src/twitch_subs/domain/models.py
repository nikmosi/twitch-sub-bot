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
    login: str
    status: BroadcasterType
    since: datetime | None = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def _resolve_status_from_bool(
        self, is_subscribed: bool, tier: str | None
    ) -> BroadcasterType:
        if not is_subscribed:
            return BroadcasterType.NONE
        if tier:
            try:
                return BroadcasterType(tier)
            except ValueError:
                pass
        return BroadcasterType.AFFILIATE

    @property
    def is_subscribed(self) -> bool:
        return self.status.is_subscribable()
