"""RabbitMQ-backed event bus implementation."""

from __future__ import annotations

import asyncio
import json
import re
from collections import OrderedDict, defaultdict
from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import Any, Awaitable, DefaultDict, Dict, Self, TypeVar, cast

from aio_pika import DeliveryMode, ExchangeType, Message
from aio_pika.abc import (
    AbstractChannel,
    AbstractExchange,
    AbstractIncomingMessage,
    AbstractQueue,
    AbstractRobustConnection,
)
from aiormq import ChannelInvalidStateError
from loguru import logger

from twitch_subs.application.ports import EventBus, Handler
from twitch_subs.domain.events import DomainEvent

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


@dataclass(slots=True, kw_only=True)
class Producer:
    connection: AbstractRobustConnection

    def start(self):
        pass

    def stop(self):
        pass


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

    async def __aenter__(self) -> Self:
        await self.start()
        return self

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
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException,
        tb: TracebackType,
    ) -> None:
        self._closing = True

        if exc_type is GeneratorExit:
            try:
                # короткий таймаут, чтобы не блокировать shutdown loop
                await asyncio.wait_for(self.stop(), timeout=2)
            except (asyncio.TimeoutError, GeneratorExit):
                LOGGER.debug(
                    "GeneratorExit during event bus cleanup; quick-stop suppressed."
                )
            except Exception:
                LOGGER.exception(
                    "Error during quick cleanup of RabbitMQEventBus (suppressed)."
                )
            return

        # для обычных исключений — логируем
        if exc_type:
            LOGGER.opt(exception=exc).error("occur exception in exit event bus.")
            LOGGER.opt(exception=exc).trace(tb)

    async def stop(self) -> None:
        # Выполняем операции по очереди, чтобы уменьшить гонки и точно обработать ошибки
        try:
            # 1) Отмена consumer (может делать RPC -> обрабатываем отдельно)
            if self._queue is not None and self._consumer_tag is not None:
                try:
                    # Пытаемся заранее обнаружить, закрыт ли канал, чтобы избежать RPC
                    channel = getattr(self._queue, "channel", None) or getattr(
                        self._queue, "_channel", None
                    )
                    if channel is None or getattr(channel, "is_closed", False):
                        LOGGER.debug(
                            "stop: queue channel already closed; skipping cancel()"
                        )
                    else:
                        await asyncio.wait_for(
                            self._queue.cancel(self._consumer_tag),
                            timeout=self._stop_timeout,
                        )
                except ChannelInvalidStateError:
                    LOGGER.debug(
                        "stop: channel invalid state while cancelling consumer (suppressed)"
                    )
                except asyncio.TimeoutError:
                    LOGGER.warning("stop: timeout while cancelling consumer")
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    LOGGER.opt(exception=e).exception(
                        "stop: error while closing consumer"
                    )
                finally:
                    self._consumer_tag = None

            # 2) Закрыть publish_channel
            if self._publish_channel is not None:
                try:
                    await asyncio.wait_for(
                        self._publish_channel.close(), timeout=self._stop_timeout
                    )
                except ChannelInvalidStateError:
                    LOGGER.debug(
                        "stop: publish_channel already invalid/closed (suppressed)"
                    )
                except asyncio.TimeoutError:
                    LOGGER.warning("stop: timeout while closing publish_channel")
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    LOGGER.opt(exception=e).exception(
                        "stop: error while closing publish_channel"
                    )
                finally:
                    self._publish_channel = None

            # 3) Закрыть consume_channel
            if self._consume_channel is not None:
                try:
                    await asyncio.wait_for(
                        self._consume_channel.close(), timeout=self._stop_timeout
                    )
                except ChannelInvalidStateError:
                    LOGGER.debug(
                        "stop: consume_channel already invalid/closed (suppressed)"
                    )
                except asyncio.TimeoutError:
                    LOGGER.warning("stop: timeout while closing consume_channel")
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    LOGGER.opt(exception=e).exception(
                        "stop: error while closing consume_channel"
                    )
                finally:
                    self._consume_channel = None

        finally:
            # Очистка ссылок
            self._queue = None
            self._exchange = None
            self._consume_exchange = None
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
            event_id: str = str(message.headers.get("event_id"))
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
