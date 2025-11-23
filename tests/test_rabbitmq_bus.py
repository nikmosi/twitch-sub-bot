from __future__ import annotations

import json
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import pytest

from twitch_subs.domain.events import UserAdded
from twitch_subs.infrastructure.event_bus.rabbitmq import (
    RabbitMQEventBus,
    _serialize_event,
)


class StubExchange:
    def __init__(self) -> None:
        self.published: list[tuple[bytes, str, dict[str, Any]]] = []
        self.is_closed = False

    async def publish(self, message: Any, routing_key: str) -> None:
        self.published.append((message.body, routing_key, message.headers))


class StubChannel:
    def __init__(self) -> None:
        self.closed = False
        self.exchange = StubExchange()

    @property
    def is_closed(self) -> bool:
        return self.closed

    async def declare_exchange(self, name: str, *_: Any, **__: Any) -> StubExchange:
        return self.exchange

    async def set_qos(self, **__: Any) -> None:  # pragma: no cover - no-op
        return None

    async def declare_queue(self, name: str | None = None, **__: Any) -> "StubQueue":
        queue = StubQueue(name or "queue")
        return queue

    async def close(self) -> None:
        self.closed = True


class StubConnection:
    def __init__(self, channel: StubChannel) -> None:
        self._channel = channel
        self.closed = False

    @property
    def is_closed(self) -> bool:
        return self.closed

    async def channel(self) -> StubChannel:
        return self._channel

    async def close(self) -> None:
        self.closed = True


@dataclass
class StubQueue:
    name: str
    declaration_result: object | None = None

    def __post_init__(self) -> None:
        self.declaration_result = object()
        self.bindings: list[tuple[Any, str]] = []
        self.consumers: list[Any] = []
        self.cancelled: list[str] = []

    async def bind(self, exchange: Any, routing_key: str) -> None:
        self.bindings.append((exchange, routing_key))

    async def consume(self, callback: Any) -> str:
        self.consumers.append(callback)
        return "consumer-tag"

    async def cancel(self, tag: str) -> None:
        self.cancelled.append(tag)


class StubMessage:
    def __init__(self, body: bytes, headers: dict[str, Any]) -> None:
        self.body = body
        self.headers = headers
        self.processed: list[bool] = []

    @asynccontextmanager
    async def process(self, *, requeue: bool = True):
        try:
            yield
        finally:
            self.processed.append(requeue)


@pytest.mark.asyncio
async def test_publish_uses_exchange(monkeypatch: pytest.MonkeyPatch) -> None:
    bus = RabbitMQEventBus("amqp://example")
    channel = StubChannel()
    connection = StubConnection(channel)

    bus._connection = connection
    bus._publish_channel = channel
    bus._exchange = channel.exchange

    event = UserAdded(login="alice")
    await bus.publish(event)

    assert channel.exchange.published
    body, routing_key, headers = channel.exchange.published[0]
    assert json.loads(body)["payload"]["login"] == "alice"
    assert routing_key == "domain.user.added"
    assert headers["event_id"] == event.id


@pytest.mark.asyncio
async def test_start_binds_subscribed_handlers(monkeypatch: pytest.MonkeyPatch) -> None:
    bus = RabbitMQEventBus("amqp://example")
    queue = StubQueue("events")
    exchange = StubExchange()

    async def fake_ensure_connection() -> None:
        return None

    async def fake_ensure_consumer() -> None:
        bus._queue = queue
        bus._consume_exchange = exchange

    bus.subscribe(UserAdded, lambda _: None)
    monkeypatch.setattr(bus, "_ensure_connection", fake_ensure_connection)
    monkeypatch.setattr(bus, "_ensure_consumer", fake_ensure_consumer)

    async with bus:
        assert queue.bindings == [(exchange, "domain.user.added")]
        assert bus._consumer_tag == "consumer-tag"


@pytest.mark.asyncio
async def test_stop_closes_resources(monkeypatch: pytest.MonkeyPatch) -> None:
    bus = RabbitMQEventBus("amqp://example")
    queue = StubQueue("events")
    channel = StubChannel()
    connection = StubConnection(channel)

    bus._queue = queue
    bus._consumer_tag = "tag"
    bus._publish_channel = channel
    bus._consume_channel = channel
    bus._connection = connection

    await bus.__aexit__(None, None, None)

    assert queue.cancelled == ["tag"]
    assert channel.closed
    assert connection.closed


@pytest.mark.asyncio
async def test_handle_message_deduplicates_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handled: list[UserAdded] = []

    bus = RabbitMQEventBus("amqp://example")

    async def handler(event: UserAdded) -> None:
        handled.append(event)

    bus.subscribe(UserAdded, handler)

    payload = _serialize_event(UserAdded(login="bob"))
    body = json.dumps(payload).encode()
    message = StubMessage(body, headers={"event_id": payload["id"]})

    await bus._on_message(message)
    await bus._on_message(message)

    assert len(handled) == 1
    assert message.processed == [True, True]
