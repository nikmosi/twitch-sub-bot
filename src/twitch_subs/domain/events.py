import uuid
from datetime import datetime, timezone
from typing import Sequence

from pydantic import BaseModel, ConfigDict, Field

from twitch_subs.domain.models import BroadcasterType


def _new_id() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DomainEvent(BaseModel):
    id: str = Field(default_factory=_new_id)
    occurred_at: datetime = Field(default_factory=_utcnow)

    @classmethod
    def name(cls) -> str:
        return cls.__name__

    model_config = ConfigDict(
        frozen=True,
        # use_enum_values=True,
        ser_json_timedelta="float",  # typos: ignore
        extra="forbid",
    )


class UserBecomeSubscribtable(DomainEvent):
    login: str
    current_state: BroadcasterType


class LoopChecked(DomainEvent):
    logins: Sequence[str]


class LoopCheckFailed(DomainEvent):
    logins: Sequence[str]
    error: str


class OnceChecked(DomainEvent):
    login: str
    current_state: BroadcasterType


class UserError(DomainEvent):
    login: str
    exception: str


class UserAdded(DomainEvent):
    login: str


class UserRemoved(DomainEvent):
    login: str


class DayChanged(DomainEvent):
    pass
