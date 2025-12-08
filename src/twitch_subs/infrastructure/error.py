from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from twitch_subs.errors import AppError


@dataclass(frozen=True, slots=True, kw_only=True)
class InfraError(AppError):
    """Base exception for infrastructure layer."""


@dataclass(frozen=True, slots=True, kw_only=True)
class WatchListIsEmpty(InfraError):
    message: str = field(init=False, default="Watchlist is empty")
    code: str = field(init=False, default="INFRA_WATCHLIST_EMPTY")


@dataclass(frozen=True, slots=True, kw_only=True)
class AsyncTelegramNotifyError(InfraError):
    exception: Exception
    message: str = field(init=False)
    code: str = field(init=False, default="INFRA_TELEGRAM_NOTIFY_FAILED")

    def __post_init__(self) -> None:  # pragma: no cover - formatting helper
        object.__setattr__(
            self, "message", f"Async telegram notification failed: {self.exception}"
        )
        object.__setattr__(self, "context", {"error": repr(self.exception)})


@dataclass(frozen=True, slots=True, kw_only=True)
class CantGetCurrentEventLoop(InfraError):
    message: str = field(init=False, default="Can't get event loop.")
    code: str = field(init=False, default="INFRA_EVENT_LOOP_MISSING")


@dataclass(frozen=True, slots=True, kw_only=True)
class CantExtractNicknama(InfraError):
    nickname: str
    message: str = field(init=False)
    code: str = field(init=False, default="INFRA_NICKNAME_PARSE_FAILED")

    def __post_init__(self) -> None:  # pragma: no cover - formatting helper
        object.__setattr__(
            self, "message", f"Can't extract nickname from {self.nickname}"
        )
        object.__setattr__(self, "context", {"nickname": self.nickname})


@dataclass(frozen=True, slots=True, kw_only=True)
class EventBusStopError(InfraError):
    message: str
    context: dict[str, Any] | None = None
    code: str = field(init=False, default="INFRA_EVENT_BUS_STOP_FAILED")


@dataclass(frozen=True, slots=True, kw_only=True)
class NotificationDeliveryError(InfraError):
    message: str
    context: dict[str, Any] | None = None
    code: str = field(init=False, default="INFRA_NOTIFICATION_FAILED")


@dataclass(frozen=True, slots=True, kw_only=True)
class ProducerCloseError(InfraError):
    message: str
    context: dict[str, Any] | None = None
    code: str = field(init=False, default="INFRA_PRODUCER_CLOSE_FAILED")


@dataclass(frozen=True, slots=True, kw_only=True)
class ConsumerStopError(InfraError):
    message: str
    context: dict[str, Any] | None = None
    code: str = field(init=False, default="INFRA_CONSUMER_STOP_FAILED")
