from __future__ import annotations

from dataclasses import InitVar, dataclass, field
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
    tier: InitVar[BroadcasterType | str]
    _broadcaster: BroadcasterType = field(init=False, repr=False)

    def __post_init__(self, tier: BroadcasterType | str) -> None:
        broadcaster = tier if isinstance(tier, BroadcasterType) else BroadcasterType(tier)
        object.__setattr__(self, "_broadcaster", broadcaster)

    @property
    def broadcaster(self) -> BroadcasterType:
        return self._broadcaster

    @property
    def tier(self) -> str:
        return self._broadcaster.value


@dataclass(frozen=True, slots=True)
class SubState:
    login: str
    status: BroadcasterType | bool
    since: datetime | None = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    tier: InitVar[str | None] = None
    _tier_value: str | None = field(init=False, repr=False)

    def __post_init__(self, tier: str | None) -> None:
        status = self.status
        if isinstance(status, bool):
            broadcaster = self._resolve_status_from_bool(status, tier)
            object.__setattr__(self, "status", broadcaster)
        else:
            broadcaster = status

        resolved_tier = self._resolve_tier(broadcaster, tier)
        object.__setattr__(self, "_tier_value", resolved_tier)

    def _resolve_status_from_bool(self, is_subscribed: bool, tier: str | None) -> BroadcasterType:
        if not is_subscribed:
            return BroadcasterType.NONE
        if tier:
            try:
                return BroadcasterType(tier)
            except ValueError:
                pass
        return BroadcasterType.AFFILIATE

    def _resolve_tier(self, status: BroadcasterType, tier: str | None) -> str | None:
        if not status.is_subscribable():
            return None
        if tier:
            try:
                return BroadcasterType(tier).value
            except ValueError:
                return status.value
        return status.value

    @property
    def is_subscribed(self) -> bool:
        return self.status.is_subscribable()

    @property
    def tier(self) -> str | None:
        return self._tier_value


