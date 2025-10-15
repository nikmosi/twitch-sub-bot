import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Sequence


from twitch_subs.domain.models import BroadcasterType


def _new_id() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True, kw_only=True)
class DomainEvent:
    id: str = field(default_factory=_new_id)
    occurred_at: datetime = field(default_factory=_utcnow)

    def name(self) -> str:
        return type(self).__name__


@dataclass(frozen=True, slots=True, kw_only=True)
class UserBecomeSubscribtable(DomainEvent):
    login: str
    current_state: BroadcasterType


@dataclass(frozen=True, slots=True, kw_only=True)
class LoopChecked(DomainEvent):
    logins: Sequence[str]


@dataclass(frozen=True, slots=True, kw_only=True)
class LoopCheckFailed(DomainEvent):
    logins: Sequence[str]
    error: str


@dataclass(frozen=True, slots=True, kw_only=True)
class OnceChecked(DomainEvent):
    login: str
    current_state: BroadcasterType


@dataclass(frozen=True, slots=True, kw_only=True)
class UserAdded(DomainEvent):
    login: str


@dataclass(frozen=True, slots=True, kw_only=True)
class UserRemoved(DomainEvent):
    login: str


@dataclass(frozen=True, slots=True, kw_only=True)
class DayChanged(DomainEvent):
    pass
