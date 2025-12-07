"""RabbitMQ-backed event bus implementation."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from types import TracebackType
from typing import Self, TypeVar

from aio_pika import DeliveryMode, ExchangeType, Message
from aio_pika.abc import (
    AbstractChannel,
    AbstractExchange,
    AbstractRobustConnection,
)
from loguru import logger

from twitch_subs.domain.events import DomainEvent
from twitch_subs.infrastructure.event_bus.rabbitmq.utils import (
    routing_key_from_type,
    serialize_event,
)

LOGGER = logger

T = TypeVar("T", bound=DomainEvent)


@dataclass(slots=True, kw_only=True)
class Producer:
    """Только публикация событий в RabbitMQ."""

    connection: AbstractRobustConnection
    exchange_name: str = "twitch_subs.events"

    _channel: AbstractChannel | None = field(init=False, default=None)
    _exchange: AbstractExchange | None = field(init=False, default=None)
    _lock: asyncio.Lock = field(init=False, default_factory=asyncio.Lock)

    async def __aenter__(self) -> Self:
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        # Для продьюсера обычно достаточно мягко закрыть канал
        await self.stop()

    async def start(self) -> None:
        # Можно лениво, но "прогрев" канала/экченджа не мешает
        await self._ensure_exchange()

    async def stop(self) -> None:
        if self._channel is not None:
            try:
                await self._channel.close()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                LOGGER.opt(exception=e).exception(
                    "producer: error while closing channel"
                )
            finally:
                self._channel = None
                self._exchange = None

    async def _ensure_exchange(self) -> AbstractExchange:
        async with self._lock:
            if self._channel is None or self._channel.is_closed:
                self._channel = await self.connection.channel()
                self._exchange = None

            if self._exchange is None:
                self._exchange = await self._channel.declare_exchange(
                    self.exchange_name,
                    ExchangeType.TOPIC,
                    durable=True,
                )

            return self._exchange

    async def publish(self, *events: DomainEvent) -> None:
        if not events:
            return

        exchange = await self._ensure_exchange()

        for event in events:
            body = json.dumps(
                serialize_event(event),
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
            message = Message(
                body=body,
                headers={"event_id": event.id},
                delivery_mode=DeliveryMode.PERSISTENT,
            )
            routing_key = routing_key_from_type(type(event))
            await exchange.publish(message, routing_key=routing_key)
