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


class SubState(ConfiguredBaseModel):
    login: str
    broadcaster_type: BroadcasterType = BroadcasterType.NONE
    since: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_subscribed(self) -> bool:
        return self.broadcaster_type.is_subscribable()
