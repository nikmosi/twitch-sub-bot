import asyncio
from collections.abc import Iterable, Sequence

import httpx
import pytest

from twitch_subs.application.error import WatcherRunError
from twitch_subs.application.logins import LoginsProvider
from twitch_subs.application.ports import (
    NotifierProtocol,
    SubscriptionStateRepo,
    TwitchClientProtocol,
)
from twitch_subs.application.watcher import Watcher
from twitch_subs.domain.events import (
    LoopCheckFailed,
    LoopChecked,
    OnceChecked,
    UserBecameSubscribable,
)
from twitch_subs.domain.models import BroadcasterType, SubState, UserRecord
from twitch_subs.infrastructure.event_bus.inmemory import InMemoryEventBus


class FakeTwitch(TwitchClientProtocol):
    def __init__(self, responses: dict[str, UserRecord | None]) -> None:
        self._responses = responses
        self.calls: list[str | tuple[str, ...]] = []

    async def get_users_by_login(self, logins: str | Sequence[str]) -> list[UserRecord]:
        if isinstance(logins, str):
            self.calls.append(logins)
            user = self._responses[logins]
            return [user] if user is not None else []
        self.calls.append(tuple(logins))
        return [
            self._responses[item]
            for item in logins
            if self._responses[item] is not None
        ]


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


class FakeNotifier(NotifierProtocol):
    def __init__(self) -> None:
        self.started = 0
        self.stopped = 0

    async def notify_about_change(
        self, login, current_state, display_name=None
    ) -> None:  # pragma: no cover - unused
        raise NotImplementedError

    async def notify_about_start(self) -> None:
        self.started += 1

    async def notify_about_stop(self) -> None:
        self.stopped += 1

    async def notify_report(
        self, states, checks: int, errors: int, missing_logins
    ) -> None:  # pragma: no cover - unused
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


async def _record_events(
    bus: InMemoryEventBus,
) -> tuple[
    list[UserBecameSubscribable],
    list[OnceChecked],
    list[LoopChecked],
    list[LoopCheckFailed],
]:
    sub_events: list[UserBecameSubscribable] = []
    checked_events: list[OnceChecked] = []
    loop_checked_events: list[LoopChecked] = []
    failed_events: list[LoopCheckFailed] = []

    async def on_subscribed(event: UserBecameSubscribable) -> None:
        sub_events.append(event)

    async def on_checked(event: OnceChecked) -> None:
        checked_events.append(event)

    async def on_loop_checked(event: LoopChecked) -> None:
        loop_checked_events.append(event)

    async def on_failed(event: LoopCheckFailed) -> None:
        failed_events.append(event)

    bus.subscribe(UserBecameSubscribable, on_subscribed)
    bus.subscribe(OnceChecked, on_checked)
    bus.subscribe(LoopChecked, on_loop_checked)
    bus.subscribe(LoopCheckFailed, on_failed)

    return sub_events, checked_events, loop_checked_events, failed_events


@pytest.mark.asyncio
async def test_run_once_detects_subscription_change() -> None:
    user = UserRecord(
        id="1",
        login="foo",
        display_name="Foo",
        broadcaster_type=BroadcasterType.AFFILIATE,
    )
    twitch = FakeTwitch({"foo": user})
    repo = FakeRepo([SubState(login="foo", broadcaster_type=BroadcasterType.NONE)])
    bus = InMemoryEventBus()
    sub_events, checked_events, loop_checked_events, _ = await _record_events(bus)
    watcher = Watcher(twitch, FakeNotifier(), repo, bus)

    await watcher.run_once(["foo"])

    assert len(sub_events) == 1
    assert sub_events[0].login == "foo"
    assert len(checked_events) == 1
    assert checked_events[0].login == "foo"
    assert len(loop_checked_events) == 1
    assert tuple(loop_checked_events[0].found_logins) == ("foo",)
    assert tuple(loop_checked_events[0].missing_logins) == ()
    assert repo._states["foo"].broadcaster_type is BroadcasterType.AFFILIATE
    assert repo.set_many_calls


@pytest.mark.asyncio
async def test_run_once_skips_missing_users() -> None:
    twitch = FakeTwitch({"foo": None})
    repo = FakeRepo()
    bus = InMemoryEventBus()
    (
        sub_events,
        checked_events,
        loop_checked_events,
        failed_events,
    ) = await _record_events(bus)
    watcher = Watcher(twitch, FakeNotifier(), repo, bus)

    await watcher.run_once(["foo"])

    assert repo.set_many_calls == [[]]
    assert sub_events == []
    assert checked_events == []
    assert failed_events == []
    assert len(loop_checked_events) == 1
    assert tuple(loop_checked_events[0].found_logins) == ()
    assert tuple(loop_checked_events[0].missing_logins) == ("foo",)


@pytest.mark.asyncio
async def test_run_once_ignores_missing_user_for_existing_state() -> None:
    twitch = FakeTwitch({"foo": None})
    repo = FakeRepo([SubState(login="foo", broadcaster_type=BroadcasterType.AFFILIATE)])
    bus = InMemoryEventBus()
    (
        sub_events,
        checked_events,
        loop_checked_events,
        failed_events,
    ) = await _record_events(bus)
    watcher = Watcher(twitch, FakeNotifier(), repo, bus)

    await watcher.run_once(["foo"])

    assert sub_events == []
    assert checked_events == []
    assert failed_events == []
    assert repo._states["foo"].is_subscribed is True
    assert len(loop_checked_events) == 1
    assert tuple(loop_checked_events[0].found_logins) == ()
    assert tuple(loop_checked_events[0].missing_logins) == ("foo",)


@pytest.mark.asyncio
async def test_run_once_reports_found_and_missing_users() -> None:
    user = UserRecord(
        id="1",
        login="foo",
        display_name="Foo",
        broadcaster_type=BroadcasterType.AFFILIATE,
    )
    twitch = FakeTwitch({"foo": user, "bar": None})
    repo = FakeRepo()
    bus = InMemoryEventBus()
    _, checked_events, loop_checked_events, failed_events = await _record_events(bus)
    watcher = Watcher(twitch, FakeNotifier(), repo, bus)

    await watcher.run_once(["foo", "bar"])

    assert failed_events == []
    assert [event.login for event in checked_events] == ["foo"]
    assert len(loop_checked_events) == 1
    assert tuple(loop_checked_events[0].found_logins) == ("foo",)
    assert tuple(loop_checked_events[0].missing_logins) == ("bar",)


@pytest.mark.asyncio
async def test_run_once_timeout_publishes_only_failure_event() -> None:
    twitch = FakeTwitch({"foo": None})
    repo = FakeRepo()
    bus = InMemoryEventBus()
    _, _, loop_checked_events, failed_events = await _record_events(bus)
    watcher = Watcher(twitch, FakeNotifier(), repo, bus)

    async def raise_timeout(logins: Sequence[str]) -> list[UserRecord]:
        raise httpx.TimeoutException("boom")

    watcher.check_logins = raise_timeout  # type: ignore[assignment]

    await watcher.run_once(["foo"])

    assert len(failed_events) == 1
    assert failed_events[0].logins == ["foo"]
    assert failed_events[0].error == "boom"
    assert loop_checked_events == []
    assert repo.set_many_calls == []


@pytest.mark.asyncio
async def test_watch_publishes_failures_and_stops(
    caplog: pytest.LogCaptureFixture,
) -> None:
    twitch = FakeTwitch({"foo": None})
    repo = FakeRepo()
    bus = InMemoryEventBus()
    _, _, _, failed_events = await _record_events(bus)
    notifier = FakeNotifier()
    watcher = Watcher(twitch, notifier, repo, bus)

    async def failing_run_once(logins: Sequence[str]) -> bool:
        raise RuntimeError("boom")

    watcher.run_once = failing_run_once  # type: ignore[assignment]

    stop_event = asyncio.Event()
    provider = StaticLogins(["foo"])

    async def trigger_stop() -> None:
        await asyncio.sleep(0.01)
        stop_event.set()

    with pytest.raises(WatcherRunError):
        task = asyncio.create_task(
            watcher.watch(provider, interval=0.1, stop_event=stop_event)
        )
        stopper = asyncio.create_task(trigger_stop())
        await asyncio.gather(task, stopper)

    assert notifier.started == 1 and notifier.stopped == 1
    assert failed_events and failed_events[0].error == "boom"


@pytest.mark.asyncio
async def test_watch_handles_timeout() -> None:
    twitch = FakeTwitch({"foo": None})
    repo = FakeRepo()
    bus = InMemoryEventBus()
    notifier = FakeNotifier()
    watcher = Watcher(twitch, notifier, repo, bus)

    stop_event = asyncio.Event()
    provider = StaticLogins(["foo"])

    async def controlled_run_once(logins: Sequence[str]) -> bool:
        asyncio.get_running_loop().call_later(0.02, stop_event.set)
        return False

    watcher.run_once = controlled_run_once  # type: ignore[assignment]

    await asyncio.wait_for(
        watcher.watch(provider, interval=0.01, stop_event=stop_event), timeout=0.1
    )

    assert notifier.started == 1 and notifier.stopped == 1
