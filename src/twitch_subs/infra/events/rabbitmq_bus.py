"""RabbitMQ-backed event bus implementation."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections import OrderedDict, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Callable, DefaultDict, Dict, TypeVar, cast

import aio_pika
from aio_pika import (
    DeliveryMode,
    Exchange,
    ExchangeType,
    Message,
    RobustChannel,
    RobustConnection,
    RobustQueue,
)
from aio_pika.abc import AbstractIncomingMessage

from twitch_subs.application.ports import EventBus, Handler
from twitch_subs.domain.events import (
    DayChanged,
    DomainEvent,
    LoopChecked,
    LoopCheckFailed,
    OnceChecked,
    UserAdded,
    UserBecomeSubscribtable,
    UserRemoved,
)
from twitch_subs.domain.models import BroadcasterType

LOGGER = logging.getLogger(__name__)

T = TypeVar("T", bound=DomainEvent)

_EVENT_VERSION = 1


@dataclass(frozen=True)
class EventDescriptor:
    routing_key: str
    to_payload: Callable[[DomainEvent], dict[str, Any]]
    from_payload: Callable[[dict[str, Any]], dict[str, Any]]


def _enum_to_value(value: Any) -> Any:
    if isinstance(value, BroadcasterType):
        return value.value
    if isinstance(value, (list, tuple)):
        return list(value)
    return value


def _default_to_payload(event: DomainEvent) -> dict[str, Any]:
    data = asdict(event)
    data.pop("id", None)
    data.pop("occurred_at", None)
    return {key: _enum_to_value(val) for key, val in data.items()}


def _identity_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return dict(payload)


_EVENT_REGISTRY: Dict[type[DomainEvent], EventDescriptor] = {
    DayChanged: EventDescriptor(
        routing_key="domain.day.changed",
        to_payload=lambda event: {},
        from_payload=lambda payload: {},
    ),
    LoopChecked: EventDescriptor(
        routing_key="domain.loop.checked",
        to_payload=_default_to_payload,
        from_payload=lambda payload: {"logins": tuple(payload["logins"])},
    ),
    LoopCheckFailed: EventDescriptor(
        routing_key="domain.loop.failed",
        to_payload=_default_to_payload,
        from_payload=lambda payload: {
            "logins": tuple(payload["logins"]),
            "error": payload["error"],
        },
    ),
    OnceChecked: EventDescriptor(
        routing_key="domain.once.checked",
        to_payload=_default_to_payload,
        from_payload=lambda payload: {
            "login": payload["login"],
            "current_state": BroadcasterType(payload["current_state"]),
        },
    ),
    UserBecomeSubscribtable: EventDescriptor(
        routing_key="domain.user.subscribable",
        to_payload=_default_to_payload,
        from_payload=lambda payload: {
            "login": payload["login"],
            "current_state": BroadcasterType(payload["current_state"]),
        },
    ),
    UserAdded: EventDescriptor(
        routing_key="domain.user.added",
        to_payload=_default_to_payload,
        from_payload=_identity_payload,
    ),
    UserRemoved: EventDescriptor(
        routing_key="domain.user.removed",
        to_payload=_default_to_payload,
        from_payload=_identity_payload,
    ),
}

_EVENT_BY_NAME: Dict[str, type[DomainEvent]] = {
    event_type.__name__: event_type for event_type in _EVENT_REGISTRY
}


def _serialize_event(event: DomainEvent) -> dict[str, Any]:
    descriptor = _EVENT_REGISTRY[type(event)]
    return {
        "id": event.id,
        "occurred_at": event.occurred_at.isoformat(),
        "name": event.name(),
        "version": _EVENT_VERSION,
        "payload": descriptor.to_payload(event),
    }


def _deserialize_event(data: dict[str, Any]) -> DomainEvent:
    name = data["name"]
    event_type = _EVENT_BY_NAME[name]
    descriptor = _EVENT_REGISTRY[event_type]
    payload = descriptor.from_payload(cast(dict[str, Any], data.get("payload", {})))
    payload.update(
        {
            "id": data["id"],
            "occurred_at": datetime.fromisoformat(data["occurred_at"]),
        }
    )
    return event_type(**payload)


class RabbitMQEventBus(EventBus):
    """Event bus backed by RabbitMQ."""

    def __init__(
        self,
        url: str,
        *,
        exchange: str = "twitch_subs.events",
        queue_name: str | None = None,
        prefetch_count: int = 10,
        dedup_capacity: int = 1024,
    ) -> None:
        self._url = url
        self._exchange_name = exchange
        self._queue_name = queue_name
        self._prefetch_count = prefetch_count
        self._dedup_capacity = dedup_capacity
        self._handlers: DefaultDict[type[DomainEvent], list[Handler[Any]]] = (
            defaultdict(list)
        )
        self._connection: RobustConnection | None = None
        self._publish_channel: RobustChannel | None = None
        self._consume_channel: RobustChannel | None = None
        self._exchange: Exchange | None = None
        self._consume_exchange: Exchange | None = None
        self._queue: RobustQueue | None = None
        self._consumer_tag: str | None = None
        self._connection_lock = asyncio.Lock()
        self._closing = False
        self._deduplication: OrderedDict[str, None] = OrderedDict()

    def subscribe(self, event_type: type[T], handler: Handler[T]) -> None:
        self._handlers[event_type].append(handler)
        if self._queue is not None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:  # pragma: no cover - no running loop
                return
            loop.create_task(self._bind_event(event_type))

    async def publish(self, *events: DomainEvent) -> None:
        if not events:
            return
        exchange = await self._get_publish_exchange()
        for event in events:
            descriptor = _EVENT_REGISTRY[type(event)]
            body = json.dumps(_serialize_event(event)).encode("utf-8")
            message = Message(
                body=body,
                headers={"event_id": event.id},
                delivery_mode=DeliveryMode.PERSISTENT,
            )
            await exchange.publish(message, routing_key=descriptor.routing_key)

    async def start(self) -> None:
        await self._ensure_connection()
        await self._ensure_consumer()
        for event_type in list(self._handlers.keys()):
            await self._bind_event(event_type)
        if self._queue is not None and self._consumer_tag is None:
            self._consumer_tag = await self._queue.consume(self._on_message)

    async def stop(self) -> None:
        self._closing = True
        if self._queue is not None and self._consumer_tag is not None:
            with contextlib.suppress(Exception):  # pragma: no cover - cleanup
                await self._queue.cancel(self._consumer_tag)
        self._consumer_tag = None
        if self._publish_channel is not None:
            with contextlib.suppress(Exception):
                await self._publish_channel.close()
        if self._consume_channel is not None:
            with contextlib.suppress(Exception):
                await self._consume_channel.close()
        if self._connection is not None:
            with contextlib.suppress(Exception):
                await self._connection.close()
        self._queue = None
        self._exchange = None
        self._consume_exchange = None
        self._publish_channel = None
        self._consume_channel = None
        self._connection = None
        self._closing = False

    async def _ensure_connection(self) -> None:
        async with self._connection_lock:
            if self._connection is None or self._connection.is_closed:
                self._connection = await aio_pika.connect_robust(self._url)
                self._publish_channel = None
                self._consume_channel = None
                self._exchange = None
                self._consume_exchange = None
                self._queue = None

    async def _get_publish_exchange(self) -> aio_pika.Exchange:
        await self._ensure_connection()
        if self._connection is None:
            raise RuntimeError("Failed to establish RabbitMQ connection")
        if self._publish_channel is None or self._publish_channel.is_closed:
            self._publish_channel = await self._connection.channel()
        if self._exchange is None or self._exchange.is_closed:
            self._exchange = await self._publish_channel.declare_exchange(
                self._exchange_name, ExchangeType.TOPIC, durable=True
            )
        return self._exchange

    async def _ensure_consumer(self) -> None:
        if self._connection is None:
            raise RuntimeError("RabbitMQ connection is not initialised")
        if self._consume_channel is None or self._consume_channel.is_closed:
            self._consume_channel = await self._connection.channel()
            await self._consume_channel.set_qos(prefetch_count=self._prefetch_count)
        if self._consume_exchange is None or self._consume_exchange.is_closed:
            self._consume_exchange = await self._consume_channel.declare_exchange(
                self._exchange_name, ExchangeType.TOPIC, durable=True
            )
        if self._queue is None or self._queue.declaration_result is None:
            self._queue = await self._consume_channel.declare_queue(
                name=self._queue_name,
                durable=self._queue_name is not None,
                auto_delete=self._queue_name is None,
                exclusive=self._queue_name is None,
            )

    async def _bind_event(self, event_type: type[DomainEvent]) -> None:
        descriptor = _EVENT_REGISTRY.get(event_type)
        if descriptor is None or self._queue is None or self._consume_exchange is None:
            return
        await self._queue.bind(
            self._consume_exchange, routing_key=descriptor.routing_key
        )

    async def _on_message(self, message: AbstractIncomingMessage) -> None:
        async with message.process(requeue=not self._closing):
            data = json.loads(message.body)
            event_id = message.headers.get("event_id") or data.get("id")
            if isinstance(event_id, bytes):
                event_id = event_id.decode("utf-8")
            if event_id and event_id in self._deduplication:
                return
            event = _deserialize_event(data)
            await self._dispatch(event)
            if event_id:
                self._deduplication[event_id] = None
                if len(self._deduplication) > self._dedup_capacity:
                    self._deduplication.popitem(last=False)

    async def _dispatch(self, event: DomainEvent) -> None:
        handlers: list[Handler[Any]] = []
        for event_type, registered in self._handlers.items():
            if isinstance(event, event_type):
                handlers.extend(registered)
        for handler in handlers:
            await handler(cast(Any, event))
