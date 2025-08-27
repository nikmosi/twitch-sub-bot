from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class BroadcasterType(str, Enum):
    NONE = "None"
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
    broadcaster_type: BroadcasterType | None
    user: UserRecord | None
