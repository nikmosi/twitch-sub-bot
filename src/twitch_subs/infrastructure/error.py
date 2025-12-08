from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from twitch_subs.errors import AppError


class InfraError(AppError):
    """Base exception for infrastructure layer."""


class WatchListIsEmpty(InfraError):
    def __init__(self) -> None:
        super().__init__("Watchlist is empty", code="INFRA_WATCHLIST_EMPTY")


class AsyncTelegramNotifyError(InfraError):
    def __init__(self, exception: Exception) -> None:
        super().__init__(
            f"Async telegram notification failed: {exception}",
            code="INFRA_TELEGRAM_NOTIFY_FAILED",
            context={"error": repr(exception)},
        )
        object.__setattr__(self, "exception", exception)


class CantGetCurrentEventLoop(InfraError):
    def __init__(self) -> None:
        super().__init__("Can't get event loop.", code="INFRA_EVENT_LOOP_MISSING")


class CantExtractNicknama(InfraError):
    def __init__(self, nickname: str) -> None:
        super().__init__(
            f"Can't extract nickname from {nickname}",
            code="INFRA_NICKNAME_PARSE_FAILED",
            context={"nickname": nickname},
        )
        object.__setattr__(self, "nickname", nickname)


class EventBusStopError(InfraError):
    def __init__(self, message: str, *, context: dict[str, Any] | None = None) -> None:
        super().__init__(
            message,
            code="INFRA_EVENT_BUS_STOP_FAILED",
            context=context,
        )


class NotificationDeliveryError(InfraError):
    def __init__(self, message: str, *, context: dict[str, Any] | None = None) -> None:
        super().__init__(
            message,
            code="INFRA_NOTIFICATION_FAILED",
            context=context,
        )


class ProducerCloseError(InfraError):
    def __init__(self, message: str, *, context: dict[str, Any] | None = None) -> None:
        super().__init__(
            message,
            code="INFRA_PRODUCER_CLOSE_FAILED",
            context=context,
        )


class ConsumerStopError(InfraError):
    def __init__(self, message: str, *, context: dict[str, Any] | None = None) -> None:
        super().__init__(
            message,
            code="INFRA_CONSUMER_STOP_FAILED",
            context=context,
        )
