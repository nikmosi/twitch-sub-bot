from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from twitch_subs.errors import AppError


@dataclass(frozen=True, slots=True, kw_only=True)
class InfraError(AppError):
    """Base exception for infrastructure layer."""


@dataclass(frozen=True, slots=True, kw_only=True)
class WatchlistIsEmpty(InfraError):
    message: str = field(
        init=False,
        default="The watchlist is empty. Please add some Twitch users first.",
    )
    code: str = field(init=False, default="INFRA_WATCHLIST_EMPTY")


@dataclass(frozen=True, slots=True, kw_only=True)
class AsyncTelegramNotifyError(InfraError):
    exception: Exception
    message: str = field(init=False)
    code: str = field(init=False, default="INFRA_TELEGRAM_NOTIFY_FAILED")

    def __post_init__(self) -> None:  # pragma: no cover - formatting helper
        object.__setattr__(
            self,
            "message",
            f"Failed to send asynchronous Telegram notification: {self.exception}",
        )
        object.__setattr__(self, "context", {"error": repr(self.exception)})


@dataclass(frozen=True, slots=True, kw_only=True)
class MissingEventLoopError(InfraError):
    message: str = field(
        init=False,
        default="No running event loop found. Ensure an asyncio event loop is active.",
    )
    code: str = field(init=False, default="INFRA_EVENT_LOOP_MISSING")


@dataclass(frozen=True, slots=True, kw_only=True)
class NicknameExtractionError(InfraError):
    nickname: str
    message: str = field(init=False)
    code: str = field(init=False, default="INFRA_NICKNAME_PARSE_FAILED")

    def __post_init__(self) -> None:  # pragma: no cover - formatting helper
        object.__setattr__(
            self,
            "message",
            f"Could not extract a valid Twitch nickname from: '{self.nickname}'",
        )
        object.__setattr__(self, "context", {"nickname": self.nickname})


@dataclass(frozen=True, slots=True, kw_only=True)
class EventBusShutdownError(InfraError):
    message: str
    context: dict[str, Any] | None = None
    code: str = field(init=False, default="INFRA_EVENT_BUS_STOP_FAILED")


@dataclass(frozen=True, slots=True, kw_only=True)
class NotificationDeliveryError(InfraError):
    message: str
    context: dict[str, Any] | None = None
    code: str = field(init=False, default="INFRA_NOTIFICATION_FAILED")


@dataclass(frozen=True, slots=True, kw_only=True)
class ProducerShutdownError(InfraError):
    message: str
    context: dict[str, Any] | None = None
    code: str = field(init=False, default="INFRA_PRODUCER_CLOSE_FAILED")


@dataclass(frozen=True, slots=True, kw_only=True)
class ConsumerShutdownError(InfraError):
    message: str
    context: dict[str, Any] | None = None
    code: str = field(init=False, default="INFRA_CONSUMER_STOP_FAILED")
