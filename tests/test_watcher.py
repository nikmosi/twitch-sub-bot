import asyncio
from collections.abc import Iterable, Sequence
from datetime import datetime, timezone

import pytest

from twitch_subs.application.logins import LoginsProvider
from twitch_subs.application.ports import (
    EventBus,
    NotifierProtocol,
    SubscriptionStateRepo,
    TwitchClientProtocol,
)
from twitch_subs.application.watcher import Watcher
from twitch_subs.domain.events import (
    LoopCheckFailed,
    LoopChecked,
    OnceChecked,
    UserBecomeSubscribtable,
)
from twitch_subs.domain.models import BroadcasterType, SubState, UserRecord


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self._now = now
        self.calls: int = 0

    def now(self) -> datetime:
        self.calls += 1
        return self._now


class FakeIdProvider:
    def __init__(self) -> None:
        self.counter = 0

    def new_id(self) -> str:
        self.counter += 1
        return f"id-{self.counter}"


class FakeTwitch(TwitchClientProtocol):
    def __init__(self, responses: dict[str, UserRecord | None]) -> None:
        self._responses = responses
        self.calls: list[str] = []

    async def get_user_by_login(self, login: str) -> UserRecord | None:
        self.calls.append(login)
        return self._responses[login]


class FakeRepo(SubscriptionStateRepo):
    def __init__(self, initial: Iterable[SubState] | None = None) -> None:
        self._states = {state.login: state for state in initial or ()}
        self.set_many_calls: list[list[SubState]] = []

    def get_sub_state(self, login: str) -> SubState | None:
        return self._states.get(login)

    def upsert_sub_state(self, state: SubState) -> None:
        self._states[state.login] = state

    def set_many(self, states: Iterable[SubState]) -> None:
        collected = list(states)
        self.set_many_calls.append(collected)
        for state in collected:
            self._states[state.login] = state


class FakeEventBus(EventBus):
    def __init__(self) -> None:
        self.events: list[object] = []
        self.subscriptions: list[tuple[type[object], object]] = []

    async def publish(self, *events: object) -> None:
        self.events.extend(events)

    def subscribe(self, event_type, handler) -> None:  # pragma: no cover - unused
        self.subscriptions.append((event_type, handler))


class FakeNotifier(NotifierProtocol):
    def __init__(self) -> None:
        self.started = 0
        self.stopped = 0

    async def notify_about_change(self, status, curr) -> None:  # pragma: no cover - unused
        raise NotImplementedError

    async def notify_about_start(self) -> None:
        self.started += 1

    async def notify_about_stop(self) -> None:
        self.stopped += 1

    async def notify_report(self, states, checks: int, errors: int) -> None:  # pragma: no cover - unused
        raise NotImplementedError

    async def send_message(
        self,
        text: str,
        disable_web_page_preview: bool = True,
        disable_notification: bool = False,
    ) -> None:  # pragma: no cover - unused
        raise NotImplementedError


class StaticLogins(LoginsProvider):
    def __init__(self, logins: Sequence[str]) -> None:
        self._logins = list(logins)

    def get(self) -> list[str]:
        return list(self._logins)


@pytest.mark.asyncio
async def test_run_once_detects_subscription_change() -> None:
    user = UserRecord("1", "foo", "Foo", BroadcasterType.AFFILIATE)
    twitch = FakeTwitch({"foo": user})
    now = datetime(2024, 1, 1, tzinfo=timezone.utc)
    repo = FakeRepo([SubState("foo", BroadcasterType.NONE, updated_at=now)])
    bus = FakeEventBus()
    watcher = Watcher(
        twitch,
        FakeNotifier(),
        repo,
        bus,
        FakeClock(now),
        FakeIdProvider(),
    )

    changed = await watcher.run_once(["foo"], asyncio.Event())

    assert changed is True
    assert isinstance(bus.events[0], UserBecomeSubscribtable)
    assert isinstance(bus.events[1], OnceChecked)
    assert isinstance(bus.events[-1], LoopChecked)
    assert repo._states["foo"].status is BroadcasterType.AFFILIATE
    assert repo.set_many_calls


@pytest.mark.asyncio
async def test_run_once_stops_when_event_is_set() -> None:
    twitch = FakeTwitch({"foo": None})
    now = datetime(2024, 1, 1, tzinfo=timezone.utc)
    repo = FakeRepo()
    bus = FakeEventBus()
    watcher = Watcher(
        twitch,
        FakeNotifier(),
        repo,
        bus,
        FakeClock(now),
        FakeIdProvider(),
    )

    stop_event = asyncio.Event()
    stop_event.set()
    changed = await watcher.run_once(["foo"], stop_event)

    assert changed is False
    assert repo.set_many_calls == []
    assert bus.events == []


@pytest.mark.asyncio
async def test_run_once_handles_subscription_drop() -> None:
    twitch = FakeTwitch({"foo": None})
    now = datetime(2024, 1, 1, tzinfo=timezone.utc)
    repo = FakeRepo(
        [SubState("foo", BroadcasterType.AFFILIATE, updated_at=now)]
    )
    bus = FakeEventBus()
    watcher = Watcher(
        twitch,
        FakeNotifier(),
        repo,
        bus,
        FakeClock(now),
        FakeIdProvider(),
    )

    changed = await watcher.run_once(["foo"], asyncio.Event())

    assert changed is True
    assert not any(isinstance(event, UserBecomeSubscribtable) for event in bus.events)
    assert repo._states["foo"].is_subscribed is False


@pytest.mark.asyncio
async def test_watch_publishes_failures_and_stops() -> None:
    twitch = FakeTwitch({"foo": None})
    repo = FakeRepo()
    bus = FakeEventBus()
    notifier = FakeNotifier()
    now = datetime(2024, 1, 1, tzinfo=timezone.utc)
    watcher = Watcher(
        twitch,
        notifier,
        repo,
        bus,
        FakeClock(now),
        FakeIdProvider(),
    )

    async def failing_run_once(logins: Sequence[str], stop_event: asyncio.Event) -> bool:
        raise RuntimeError("boom")

    watcher.run_once = failing_run_once  # type: ignore[assignment]

    stop_event = asyncio.Event()
    provider = StaticLogins(["foo"])

    async def trigger_stop() -> None:
        await asyncio.sleep(0.01)
        stop_event.set()

    task = asyncio.create_task(watcher.watch(provider, interval=0.1, stop_event=stop_event))
    stopper = asyncio.create_task(trigger_stop())
    await asyncio.gather(task, stopper)

    assert notifier.started == 1 and notifier.stopped == 1
    failure_events = [event for event in bus.events if isinstance(event, LoopCheckFailed)]
    assert failure_events and failure_events[0].error == "boom"


@pytest.mark.asyncio
async def test_watch_handles_timeout() -> None:
    twitch = FakeTwitch({"foo": None})
    repo = FakeRepo()
    bus = FakeEventBus()
    notifier = FakeNotifier()
    now = datetime(2024, 1, 1, tzinfo=timezone.utc)
    watcher = Watcher(
        twitch,
        notifier,
        repo,
        bus,
        FakeClock(now),
        FakeIdProvider(),
    )

    stop_event = asyncio.Event()
    provider = StaticLogins(["foo"])

    async def controlled_run_once(logins: Sequence[str], event: asyncio.Event) -> bool:
        asyncio.get_running_loop().call_later(0.02, event.set)
        return False

    watcher.run_once = controlled_run_once  # type: ignore[assignment]

    await asyncio.wait_for(
        watcher.watch(provider, interval=0.01, stop_event=stop_event), timeout=0.1
    )

    assert notifier.started == 1 and notifier.stopped == 1
