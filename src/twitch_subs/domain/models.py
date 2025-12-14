from __future__ import annotations

from dataclasses import field
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict


class ConfiguredBaseModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class BroadcasterType(str, Enum):
    NONE = "none"
    AFFILIATE = "affiliate"
    PARTNER = "partner"

    def is_subscribable(self) -> bool:
        return self in {BroadcasterType.AFFILIATE, BroadcasterType.PARTNER}


class TwitchAppCreds(ConfiguredBaseModel):
    client_id: str
    client_secret: str


class UserRecord(ConfiguredBaseModel):
    id: str
    login: str
    display_name: str
    broadcaster_type: BroadcasterType


class LoginStatus(ConfiguredBaseModel):
    """Result of a single login check."""

    login: str
    broadcaster_type: BroadcasterType
    user: UserRecord | None


class SubState(ConfiguredBaseModel):
    login: str
    status: BroadcasterType
    since: datetime | None = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    tier: str | None = None

    @property
    def is_subscribed(self) -> bool:
        return self.status.is_subscribable()


class LoginReportInfo(ConfiguredBaseModel):
    login: str
    broadcaster: BroadcasterType = field(default=BroadcasterType.NONE)
