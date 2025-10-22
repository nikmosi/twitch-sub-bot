"""RabbitMQ-backed event bus implementation."""

from __future__ import annotations

import asyncio
import json
import re
from collections import OrderedDict, defaultdict
from datetime import datetime
from types import TracebackType
from typing import Any, Awaitable, DefaultDict, Dict, TypeVar, cast

from aio_pika import DeliveryMode, ExchangeType, Message
from aio_pika.abc import (
    AbstractChannel,
    AbstractExchange,
    AbstractIncomingMessage,
    AbstractQueue,
    AbstractRobustConnection,
)
from loguru import logger

from twitch_subs.application.ports import EventBus, Handler
from twitch_subs.domain.events import (
    DomainEvent,  # Pydantic BaseModel с полями id, occurred_at
)

LOGGER = logger

T = TypeVar("T", bound=DomainEvent)
_EVENT_VERSION = 1

_CAMEL_SPLIT = re.compile(r"[A-Z]+(?=[A-Z][a-z]|$)|[A-Z]?[a-z]+|\d+")


def _routing_key_from_type(tp: type[DomainEvent]) -> str:
    # Опциональные переопределения на классе события
    rk = getattr(tp, "ROUTING_KEY", None)
    if isinstance(rk, str) and rk:
        return rk
    prefix = getattr(tp, "ROUTING_PREFIX", "domain")
    name = tp.name()
    parts = _CAMEL_SPLIT.findall(name)
    return f"{prefix}." + ".".join(p.lower() for p in parts)


def _serialize_event(event: DomainEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "occurred_at": event.occurred_at.isoformat(),
        "name": event.name(),
        "version": _EVENT_VERSION,
        "payload": event.model_dump(mode="json", exclude={"id", "occurred_at"}),
    }


class RabbitMQEventBus(EventBus):
    """Event bus backed by RabbitMQ with auto routing keys."""

    def __init__(
        self,
        connection: AbstractRobustConnection,
        *,
        exchange: str = "twitch_subs.events",
        queue_name: str | None = None,
        prefetch_count: int = 10,
        dedup_capacity: int = 1024,
        stop_timeout: int = 5,
    ) -> None:
        self._exchange_name = exchange
        self._queue_name = queue_name
        self._prefetch_count = prefetch_count
        self._dedup_capacity = dedup_capacity
        self._stop_timeout = stop_timeout
        self._connection: AbstractRobustConnection = connection

        self._handlers: DefaultDict[type[DomainEvent], list[Handler[Any]]] = (
            defaultdict(list)
        )
        self._types_by_name: Dict[str, type[DomainEvent]] = {}

        self._publish_channel: AbstractChannel | None = None
        self._consume_channel: AbstractChannel | None = None
        self._exchange: AbstractExchange | None = None
        self._consume_exchange: AbstractExchange | None = None
        self._queue: AbstractQueue | None = None
        self._consumer_tag: str | None = None

        self._closing = False
        self._deduplication: OrderedDict[str, None] = OrderedDict()

    def subscribe(self, event_type: type[T], handler: Handler[T]) -> None:
        self._handlers[event_type].append(handler)
        self._types_by_name[event_type.name()] = event_type
        if self._queue is not None:
            asyncio.create_task(self._bind_event(event_type))

    async def publish(self, *events: DomainEvent) -> None:
        if not events:
            return
        exchange = await self._get_publish_exchange()
        for event in events:
            body = json.dumps(
                _serialize_event(event),
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
            message = Message(
                body=body,
                headers={"event_id": event.id},
                delivery_mode=DeliveryMode.PERSISTENT,
            )
            routing_key = _routing_key_from_type(type(event))
            await exchange.publish(message, routing_key=routing_key)

    async def __aenter__(self) -> None:
        return await self.start()

    async def start(self) -> None:
        await self._ensure_consumer()
        for event_type in list(self._handlers.keys()):
            await self._bind_event(event_type)
        if self._queue is not None and self._consumer_tag is None:
            self._consumer_tag = await self._queue.consume(self._on_message)

    def _close_task(self, name: str, aw: Awaitable[Any]) -> asyncio.Task[None]:
        async def runner() -> None:
            try:
                await aw
            except asyncio.CancelledError:
                raise
            except Exception as e:
                LOGGER.opt(exception=e).exception(f"stop: error while closing {name}")

        return asyncio.create_task(runner())

    async def __aexit__(
        self, exc_type: type[Exception] | None, exc: BaseException, tb: TracebackType
    ) -> None:
        self._closing = True

        if exc_type:
            logger.opt(exception=exc).error("occur exception in exit event bus.")
            logger.opt(exception=exc).trace(tb)

        return await self.stop()

    async def stop(self) -> None:
        tasks: list[asyncio.Task[None]] = []

        if self._queue is not None and self._consumer_tag is not None:
            tasks.append(
                self._close_task("consumer", self._queue.cancel(self._consumer_tag))
            )
            self._consumer_tag = None

        if self._publish_channel is not None:
            tasks.append(
                self._close_task("publish_channel", self._publish_channel.close())
            )
        if self._consume_channel is not None:
            tasks.append(
                self._close_task("consume_channel", self._consume_channel.close())
            )

        if tasks:
            done, pending = await asyncio.wait(
                tasks, timeout=self._stop_timeout, return_when=asyncio.ALL_COMPLETED
            )
            # обработать неожиданные ошибки (если runner их не проглотил)
            for t in done:
                try:
                    t.result()
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    LOGGER.opt(exception=e).exception(
                        "stop: unexpected error in close task"
                    )

            if pending:
                for t in pending:
                    t.cancel()
                # ждём повторно после отмены
                _, still_pending = await asyncio.wait(
                    pending, timeout=self._stop_timeout
                )
                if still_pending:
                    LOGGER.warning(
                        f"stop: {len(still_pending)} close task(s) stuck after cancel"
                    )

        # обнуление ссылок всегда
        self._queue = None
        self._exchange = None
        self._consume_exchange = None
        self._publish_channel = None
        self._consume_channel = None
        self._closing = False

    async def _get_publish_exchange(self) -> AbstractExchange:
        if self._publish_channel is None or self._publish_channel.is_closed:
            self._publish_channel = await self._connection.channel()
            self._exchange = None
        if self._exchange is None:
            self._exchange = await self._publish_channel.declare_exchange(
                self._exchange_name, ExchangeType.TOPIC, durable=True
            )
        return self._exchange

    async def _ensure_consumer(self) -> None:
        if self._consume_channel is None or self._consume_channel.is_closed:
            self._consume_channel = await self._connection.channel()
            await self._consume_channel.set_qos(prefetch_count=self._prefetch_count)
            self._consume_exchange = None
            self._queue = None
        if self._consume_exchange is None:
            self._consume_exchange = await self._consume_channel.declare_exchange(
                self._exchange_name, ExchangeType.TOPIC, durable=True
            )
        if self._queue is None:
            self._queue = await self._consume_channel.declare_queue(
                name=self._queue_name,
                durable=self._queue_name is not None,
                auto_delete=self._queue_name is None,
                exclusive=self._queue_name is None,
            )

    async def _bind_event(self, event_type: type[DomainEvent]) -> None:
        if self._queue is None or self._consume_exchange is None:
            return
        routing_key = _routing_key_from_type(event_type)
        await self._queue.bind(self._consume_exchange, routing_key=routing_key)

    async def _on_message(self, message: AbstractIncomingMessage) -> None:
        async with message.process(requeue=not self._closing):
            data = json.loads(message.body)

            # dedup
            event_id: str | None = None
            header_id = message.headers.get("event_id")
            if isinstance(header_id, bytes):
                event_id = header_id.decode("utf-8")
            elif header_id is not None:
                event_id = str(header_id)
            else:
                pid = data.get("id")
                event_id = (
                    pid.decode("utf-8")
                    if isinstance(pid, bytes)
                    else (str(pid) if pid is not None else None)
                )
            if event_id and event_id in self._deduplication:
                return

            # ленивое сопоставление по имени класса
            name = data.get("name")
            tp = self._types_by_name.get(name)
            if tp is None:
                LOGGER.warning(
                    f"skip unknown event {name}",
                )
                return

            event = tp.model_validate(
                {
                    **(data.get("payload") or {}),
                    "id": data["id"],
                    "occurred_at": datetime.fromisoformat(data["occurred_at"]),
                }
            )
            await self._dispatch(event)

            if event_id:
                self._remember_event_id(event_id)

    def _remember_event_id(self, event_id: str) -> None:
        self._deduplication[event_id] = None
        if len(self._deduplication) > self._dedup_capacity:
            self._deduplication.popitem(last=False)

    async def _dispatch(self, event: DomainEvent) -> None:
        handlers: list[Handler[Any]] = []
        for tp, registered in self._handlers.items():
            if isinstance(event, tp):
                handlers.extend(registered)
        for handler in handlers:
            await handler(cast(Any, event))
