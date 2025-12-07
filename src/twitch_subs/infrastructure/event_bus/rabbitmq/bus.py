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
        """
        Сохраняем старую сигнатуру: подписка на тип события.
        """
        self._consumer.subscribe(event_type, handler)

    async def publish(self, *events: DomainEvent) -> None:
        """
        Старая сигнатура publish — теперь просто делегирует в Producer.
        """
        await self._producer.publish(*events)

    async def start(self) -> None:
        """
        Запуск и продюсера, и консюмера.

        Если где-то в коде раньше делали:
            bus = RabbitMQEventBus(...)
            await bus.start()
        — это продолжит работать.
        """
        # продюсер можно не стартовать, но пусть будет симметрия
        await self._producer.start()
        await self._consumer.start()

    async def stop(self) -> None:
        """
        Остановка консюмера и продюсера.

        Сначала гасим consumer (чтобы не таскать новые сообщения),
        потом продюсер.
        """
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
        """
        Для сохранения поведения:
        - прокидываем exit в consumer (там уже есть спец-логика под GeneratorExit)
        - после этого останавливаем producer.
        """
        try:
            # отдаём право первой ночи консюмеру — у него более тонкая логика stop/closing
            try:
                await self._consumer.__aexit__(exc_type, exc, tb)
            except AttributeError:
                # на случай, если Consumer не реализует __aexit__ (например, его упростили)
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
