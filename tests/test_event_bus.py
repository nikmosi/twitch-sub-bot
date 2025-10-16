import asyncio
from datetime import datetime, timezone

import pytest

from twitch_subs.domain.events import DayChanged, LoopChecked
from twitch_subs.infrastructure.event_bus.in_memory import InMemoryEventBus


@pytest.mark.asyncio
async def test_in_memory_event_bus_dispatches_matching_events() -> None:
    bus = InMemoryEventBus()
    received: list[DayChanged] = []

    async def handler(event: DayChanged) -> None:
        received.append(event)

    bus.subscribe(DayChanged, handler)
    now = datetime(2024, 1, 1, tzinfo=timezone.utc)
    await bus.publish(
        DayChanged(id="id-1", occurred_at=now),
        LoopChecked(id="id-2", occurred_at=now, logins=("foo",)),
    )

    assert len(received) == 1
    assert isinstance(received[0], DayChanged)


@pytest.mark.asyncio
async def test_in_memory_event_bus_ignores_non_matching_events() -> None:
    bus = InMemoryEventBus()
    triggered = asyncio.Event()

    async def handler(event: LoopChecked) -> None:
        triggered.set()

    bus.subscribe(LoopChecked, handler)
    now = datetime(2024, 1, 1, tzinfo=timezone.utc)
    await bus.publish(DayChanged(id="id-3", occurred_at=now))

    assert not triggered.is_set()
