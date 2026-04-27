"""RabbitMQ-backed event bus implementation."""

from __future__ import annotations

import asyncio
import json
from collections import OrderedDict, defaultdict
from datetime import datetime
from types import TracebackType
from typing import Any, DefaultDict, Dict, Self, TypeVar, cast

from aio_pika import ExchangeType
from aio_pika.abc import (
    AbstractChannel,
    AbstractExchange,
    AbstractIncomingMessage,
    AbstractQueue,
    AbstractRobustConnection,
)
from aiormq import ChannelInvalidStateError
from loguru import logger

from twitch_subs.application.ports import Handler
from twitch_subs.domain.events import DomainEvent
from twitch_subs.infrastructure.error import ConsumerShutdownError
from twitch_subs.infrastructure.error_utils import log_and_wrap
from twitch_subs.infrastructure.event_bus.rabbitmq.utils import routing_key_from_type


T = TypeVar("T", bound=DomainEvent)


class Consumer:
    """Consumer RabbitMQ: подписки, consume, dispatch, дедуп."""

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

        self._channel: AbstractChannel | None = None
        self._exchange: AbstractExchange | None = None
        self._queue: AbstractQueue | None = None
        self._consumer_tag: str | None = None

        self._closing = False
        self._deduplication: OrderedDict[str, None] = OrderedDict()

    async def __aenter__(self) -> Self:
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._closing = True

        if exc_type is GeneratorExit:
            try:
                await asyncio.wait_for(self.stop(), timeout=2)
            except (asyncio.TimeoutError, GeneratorExit):
                logger.debug(
                    "GeneratorExit during consumer cleanup; quick-stop suppressed."
                )
            except Exception as exc:
                log_and_wrap(
                    exc,
                    ConsumerShutdownError,
                    context={"stage": "quick_cleanup", "exc_type": type(exc).__name__},
                )
            return

        if exc_type:
            logger.opt(exception=exc).error("exception in Consumer.__aexit__")
            if tb is not None:
                logger.opt(exception=exc).trace(tb)

        # В обычном кейсе имеет смысл всё-таки закрыть consumer
        await self.stop()

    def subscribe(self, event_type: type[T], handler: Handler[T]) -> None:
        self._handlers[event_type].append(handler)
        self._types_by_name[event_type.name()] = event_type
        if self._queue is not None:
            asyncio.create_task(self._bind_event(event_type))

    async def start(self) -> None:
        await self._ensure_consumer()
        for event_type in list(self._handlers.keys()):
            await self._bind_event(event_type)
        if self._queue is not None and self._consumer_tag is None:
            self._consumer_tag = await self._queue.consume(self._on_message)

    async def stop(self) -> None:
        self._closing = True
        try:
            # 1) Отмена consumer
            if self._queue is not None and self._consumer_tag is not None:
                try:
                    channel = getattr(self._queue, "channel", None) or getattr(
                        self._queue, "_channel", None
                    )
                    if channel is None or getattr(channel, "is_closed", False):
                        logger.debug(
                            "[RabbitMQ-Consumer] Channel already closed; skipping queue cancel for tag={}",
                            self._consumer_tag,
                        )
                    else:
                        await asyncio.wait_for(
                            self._queue.cancel(self._consumer_tag),
                            timeout=self._stop_timeout,
                        )
                except ChannelInvalidStateError:
                    logger.debug(
                        "[RabbitMQ-Consumer] Channel invalid/closed during queue cancel (suppressed). tag={}",
                        self._consumer_tag,
                    )
                except asyncio.TimeoutError:
                    logger.warning(
                        "[RabbitMQ-Consumer] Timeout while cancelling the queue consumer (tag={})",
                        self._consumer_tag,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    log_and_wrap(
                        exc,
                        ConsumerShutdownError,
                        context={
                            "stage": "queue_cancel",
                            "exc_type": type(exc).__name__,
                        },
                    )
                finally:
                    self._consumer_tag = None

            # 2) Закрыть канал
            if self._channel is not None:
                try:
                    await asyncio.wait_for(
                        self._channel.close(), timeout=self._stop_timeout
                    )
                except ChannelInvalidStateError:
                    logger.debug(
                        "[RabbitMQ-Consumer] Channel already invalid/closed on close request (suppressed)"
                    )
                except asyncio.TimeoutError:
                    logger.warning("[RabbitMQ-Consumer] Timeout while closing channel.")
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    log_and_wrap(
                        exc,
                        ConsumerShutdownError,
                        context={
                            "stage": "channel_close",
                            "exc_type": type(exc).__name__,
                        },
                    )
                finally:
                    self._channel = None

        finally:
            self._queue = None
            self._exchange = None
            self._closing = False

    async def _ensure_consumer(self) -> None:
        if self._channel is None or self._channel.is_closed:
            self._channel = await self._connection.channel()
            await self._channel.set_qos(prefetch_count=self._prefetch_count)
            self._exchange = None
            self._queue = None

        if self._exchange is None:
            self._exchange = await self._channel.declare_exchange(
                self._exchange_name, ExchangeType.TOPIC, durable=True
            )

        if self._queue is None:
            self._queue = await self._channel.declare_queue(
                name=self._queue_name,
                durable=self._queue_name is not None,
                auto_delete=self._queue_name is None,
                exclusive=self._queue_name is None,
            )

    async def _bind_event(self, event_type: type[DomainEvent]) -> None:
        if self._queue is None or self._exchange is None:
            return
        routing_key = routing_key_from_type(event_type)
        await self._queue.bind(self._exchange, routing_key=routing_key)

    async def _on_message(self, message: AbstractIncomingMessage) -> None:
        async with message.process(requeue=not self._closing):
            data = json.loads(message.body)

            # dedup
            event_id: str = str(message.headers.get("event_id"))
            if event_id and event_id in self._deduplication:
                return

            event_name = data.get("name")
            event_type = self._types_by_name.get(event_name)
            if event_type is None:
                logger.warning(
                    "[RabbitMQ-Consumer] Skipping unknown event: {} (no handler registered)",
                    event_name,
                )
                return

            event = event_type.model_validate(
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
        for event_type, registered_handlers in self._handlers.items():
            if isinstance(event, event_type):
                handlers.extend(registered_handlers)
        for handler in handlers:
            await handler(cast(Any, event))
