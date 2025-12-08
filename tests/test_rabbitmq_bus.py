from __future__ import annotations

import pytest

from twitch_subs.domain.events import UserAdded
from twitch_subs.infrastructure.event_bus.rabbitmq import RabbitMQEventBus


class StubProducer:
    def __init__(self) -> None:
        self.published: list[UserAdded] = []
        self.started = False
        self.stopped = False

    async def publish(self, *events: UserAdded) -> None:
        self.published.extend(events)

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True


class StubConsumer:
    def __init__(self) -> None:
        self.subscriptions: list[tuple[type[UserAdded], object]] = []
        self.started = False
        self.stopped = False

    def subscribe(self, event_type: type[UserAdded], handler: object) -> None:
        self.subscriptions.append((event_type, handler))

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True


@pytest.mark.asyncio
async def test_publish_delegates_to_producer() -> None:
    producer = StubProducer()
    consumer = StubConsumer()
    bus = RabbitMQEventBus(producer=producer, consumer=consumer)

    event = UserAdded(login="alice")
    await bus.publish(event)

    assert producer.published == [event]


@pytest.mark.asyncio
async def test_subscribe_and_lifecycle_calls_dependencies() -> None:
    producer = StubProducer()
    consumer = StubConsumer()
    bus = RabbitMQEventBus(producer=producer, consumer=consumer)

    handler = object()
    bus.subscribe(UserAdded, handler)  # type: ignore[arg-type]

    assert consumer.subscriptions == [(UserAdded, handler)]

    await bus.start()
    await bus.stop()

    assert producer.started and consumer.started
    assert producer.stopped and consumer.stopped
