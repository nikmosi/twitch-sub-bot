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
    status: BroadcasterType | bool | str
    since: datetime | None = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    tier: str | None = None

    def __post_init__(self) -> None:
        status = self._normalize_status(self.status, self.tier)
        tier = status.value if status.is_subscribable() else None
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "tier", tier)

    def _normalize_status(
        self, raw_status: BroadcasterType | bool | str, tier: str | None
    ) -> BroadcasterType:
        if isinstance(raw_status, BroadcasterType):
            return raw_status
        if isinstance(raw_status, bool):
            return self._resolve_status_from_bool(raw_status, tier)
        try:
            return BroadcasterType(raw_status)
        except ValueError:
            return BroadcasterType.AFFILIATE

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


@dataclass(frozen=True)
class LoginReportInfo:
    login: str
    tier: str | BroadcasterType | None
    broadcaster: BroadcasterType = field(init=False)

    def __post_init__(self) -> None:
        broadcaster = self._normalize_broadcaster(self.tier)
        normalized_tier = broadcaster.value if broadcaster.is_subscribable() else None
        object.__setattr__(self, "broadcaster", broadcaster)
        object.__setattr__(self, "tier", normalized_tier)

    @staticmethod
    def _normalize_broadcaster(
        tier: str | BroadcasterType | None,
    ) -> BroadcasterType:
        if tier is None:
            return BroadcasterType.NONE
        if isinstance(tier, BroadcasterType):
            return tier
        try:
            return BroadcasterType(tier)
        except ValueError:
            return BroadcasterType.AFFILIATE
