"""In-memory event bus for tests and development."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, DefaultDict, Deque, TypeVar

from loguru import logger

from twitch_subs.application.ports import EventBus, Handler
from twitch_subs.domain.events import DomainEvent

T = TypeVar("T", bound=DomainEvent)


@dataclass(slots=True, kw_only=True)
class InMemoryEventBus(EventBus):
    """Simple event bus dispatching events to in-process handlers."""

    _handlers: DefaultDict[type[DomainEvent], list[Handler[Any]]] = field(
        default_factory=lambda: defaultdict(list)
    )

    _idempotency_queue: Deque[DomainEvent] = field(
        default_factory=lambda: deque(maxlen=100)
    )

    async def publish(self, *events: DomainEvent) -> None:
        for event in events:
            if event in self._idempotency_queue:
                logger.warning(f"Get duplicated event {event}.")
                continue

            self._idempotency_queue.append(event)
            for event_type, handlers in self._handlers.items():
                if isinstance(event, event_type):
                    for handler in handlers:
                        await handler(event)

    def subscribe(self, event_type: type[T], handler: Handler[T]) -> None:
        self._handlers[event_type].append(handler)
