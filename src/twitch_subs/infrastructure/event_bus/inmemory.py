"""In-memory event bus for tests and development."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, DefaultDict, TypeVar, cast

from twitch_subs.application.ports import EventBus, Handler
from twitch_subs.domain.events import DomainEvent

T = TypeVar("T", bound=DomainEvent)


@dataclass(slots=True, kw_only=True)
class InMemoryEventBus(EventBus):
    """Simple event bus dispatching events to in-process handlers."""

    _handlers: DefaultDict[type[DomainEvent], list[Handler[Any]]] = field(
        default_factory=lambda: defaultdict(list)
    )

    async def publish(self, *events: DomainEvent) -> None:
        for event in events:
            for event_type, handlers in self._handlers.items():
                if isinstance(event, event_type):
                    for handler in handlers:
                        await handler(cast(Any, event))

    def subscribe(self, event_type: type[T], handler: Handler[T]) -> None:
        self._handlers[event_type].append(handler)
