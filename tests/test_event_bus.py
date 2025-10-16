from __future__ import annotations

import asyncio

import pytest

from twitch_subs.domain.events import DayChanged, LoopChecked
from twitch_subs.infra.events import InMemoryEventBus


@pytest.mark.asyncio
async def test_in_memory_event_bus_dispatches_matching_events() -> None:
    bus = InMemoryEventBus()
    received: list[DayChanged] = []

    async def handler(event: DayChanged) -> None:
        received.append(event)

    bus.subscribe(DayChanged, handler)
    await bus.publish(DayChanged(), LoopChecked(logins=("foo",)))

    assert len(received) == 1
    assert isinstance(received[0], DayChanged)


@pytest.mark.asyncio
async def test_in_memory_event_bus_ignores_non_matching_events() -> None:
    bus = InMemoryEventBus()
    triggered = asyncio.Event()

    async def handler(event: LoopChecked) -> None:
        triggered.set()

    bus.subscribe(LoopChecked, handler)
    await bus.publish(DayChanged())

    assert not triggered.is_set()
