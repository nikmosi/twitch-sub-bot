"""RabbitMQ-backed event bus implementation."""

from __future__ import annotations

import asyncio
from types import TracebackType
from typing import Self, TypeVar

from loguru import logger

from twitch_subs.application.ports import EventBus, Handler
from twitch_subs.domain.events import DomainEvent
from twitch_subs.infrastructure.event_bus.rabbitmq.consumer import Consumer
from twitch_subs.infrastructure.event_bus.rabbitmq.producer import Producer

LOGGER = logger

T = TypeVar("T", bound=DomainEvent)


class RabbitMQEventBus(EventBus):
    def __init__(
        self,
        producer: Producer,
        consumer: Consumer,
    ) -> None:
        self._producer = producer
        self._consumer = consumer

    # ========== API как раньше ==========

    def subscribe(self, event_type: type[T], handler: Handler[T]) -> None:
        self._consumer.subscribe(event_type, handler)

    async def publish(self, *events: DomainEvent) -> None:
        await self._producer.publish(*events)

    async def start(self) -> None:
        await self._producer.start()
        await self._consumer.start()

    async def stop(self) -> None:
        try:
            await self._consumer.stop()
        finally:
            await self._producer.stop()

    # ========= async context manager =========

    async def __aenter__(self) -> Self:
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        try:
            await self._consumer.stop()
        finally:
            try:
                await self._producer.stop()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                LOGGER.opt(exception=e).exception(
                    "RabbitMQEventBus: error while stopping producer in __aexit__"
                )
