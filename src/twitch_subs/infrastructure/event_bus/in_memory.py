from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, DefaultDict, TypeVar, cast, override

from twitch_subs.application.ports import EventBus, Handler
from twitch_subs.domain.events import DomainEvent

T = TypeVar("T", bound=DomainEvent)


@dataclass(frozen=True, slots=True, kw_only=True)
class InMemoryEventBus(EventBus):
    mem: DefaultDict[type[DomainEvent], list[Handler[Any]]] = field(
        default_factory=lambda: defaultdict(list)
    )

    @override
    async def publish(self, *events: DomainEvent) -> None:
        for event in events:
            for event_type, handlers in self.mem.items():
                if isinstance(event, event_type):
                    for handler in handlers:
                        await handler(cast(Any, event))

    @override
    def subscribe(self, event_type: type[T], handler: Handler[T]) -> None:
        self.mem[event_type].append(handler)
