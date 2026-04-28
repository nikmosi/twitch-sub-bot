from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Sequence

from pydantic import BaseModel, ConfigDict


class ConfiguredBaseModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class BroadcasterType(str, Enum):
    NONE = "none"
    AFFILIATE = "affiliate"
    PARTNER = "partner"

    def is_subscribable(self) -> bool:
        return self in {BroadcasterType.AFFILIATE, BroadcasterType.PARTNER}


@dataclass(frozen=True, slots=True)
class TwitchUsername:
    value: str

    _USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,25}$", re.ASCII)
    _URL_RE = re.compile(
        r"^https?://(?:(?:www|m)\.)?twitch\.tv/(?P<login>[A-Za-z0-9_]{3,25})/?$",
        re.ASCII,
    )

    def __post_init__(self) -> None:
        if not self._USERNAME_RE.fullmatch(self.value):
            raise ValueError(self.value)

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value

    @classmethod
    def parse(cls, raw: str) -> TwitchUsername:
        return cls(raw.strip())

    @classmethod
    def parse_many(cls, raw_values: Iterable[str]) -> Sequence[TwitchUsername]:
        return [cls.parse(raw) for raw in raw_values]

    @classmethod
    def parse_from_token(cls, token: str) -> TwitchUsername:
        candidate = token.strip()
        if match := cls._URL_RE.fullmatch(candidate):
            candidate = match.group("login")
        return cls(candidate)

    @classmethod
    def parse_from_text(cls, text: str) -> Sequence[TwitchUsername]:
        return [cls.parse_from_token(token) for token in text.split()]


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
