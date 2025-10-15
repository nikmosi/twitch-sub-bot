import asyncio
import contextlib
from collections import deque
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Iterable, Sequence

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
    LoopChecked,
    LoopCheckFailed,
    UserBecomeSubscribtable,
)
from twitch_subs.domain.models import (
    BroadcasterType,
    LoginReportInfo,
    LoginStatus,
    SubState,
    UserRecord,
)
from twitch_subs.infrastructure.event_bus.in_memory import InMemoryEventBus


class InMemoryStateRepo(SubscriptionStateRepo):
    def __init__(self, initial: Iterable[SubState] | None = None) -> None:
        self._states = {s.login: s for s in initial or ()}
        self.set_many_calls: list[list[SubState]] = []

    def get_sub_state(self, login: str) -> SubState | None:
        return self._states.get(login)

    def upsert_sub_state(self, state: SubState) -> None:
        self._states[state.login] = state

    def set_many(self, states: Iterable[SubState]) -> None:
        collected = [replace(s, updated_at=s.updated_at) for s in states]
        if not collected:
            return
        self.set_many_calls.append(collected)
        for state in collected:
            self._states[state.login] = state

    def list_all(self) -> list[SubState]:
        return list(self._states.values())


class DummyNotifier(NotifierProtocol):
    def __init__(self) -> None:
        self.start_called = False
        self.stop_called = False
        self.changes: list[tuple[LoginStatus, BroadcasterType]] = []
        self.reports: list[tuple[list[LoginReportInfo], int, int]] = []
        self.messages: list[str] = []

    async def notify_about_change(
        self, status: LoginStatus, curr: BroadcasterType
    ) -> None:
        self.changes.append((status, curr))

    async def notify_about_start(self) -> None:
        self.start_called = True

    async def notify_about_stop(self) -> None:
        self.stop_called = True

    async def notify_report(
        self,
        states: Sequence[LoginReportInfo],
        checks: int,
        errors: int,
    ) -> None:
        self.reports.append((list(states), checks, errors))

    async def send_message(
        self,
        text: str,
        disable_web_page_preview: bool = True,
        disable_notification: bool = False,
    ) -> None:
        self.messages.append(text)


class DummyTwitch(TwitchClientProtocol):
    def __init__(self, users: dict[str, UserRecord | None]) -> None:
        self.users = users
        self.calls: deque[str] = deque()

    async def get_user_by_login(self, login: str) -> UserRecord | None:
        self.calls.append(login)
        return self.users.get(login)


class StaticLogins(LoginsProvider):
    def __init__(self, value: list[str]) -> None:
        self.value = value
        self.calls = 0

    def get(self) -> list[str]:
        self.calls += 1
        return list(self.value)


class DummyEventBus(EventBus):
    def __init__(self) -> None:
        self.events: list[Any] = []

    async def publish(self, event: Any) -> None:
        self.events.append(event)


@pytest.mark.asyncio
async def test_check_login_found_and_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    user = UserRecord("1", "foo", "Foo", BroadcasterType.AFFILIATE)
    twitch = DummyTwitch({"foo": user, "bar": None})
    watcher = Watcher(twitch, DummyNotifier(), InMemoryStateRepo(), InMemoryEventBus())

    status = await watcher.check_login("foo")
    assert status.user == user
    assert status.broadcaster_type is BroadcasterType.AFFILIATE

    missing = await watcher.check_login("bar")
    assert missing.user is None
    assert missing.broadcaster_type is BroadcasterType.NONE


@pytest.mark.asyncio
async def test_run_once_transitions_and_notifies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixed = datetime(2024, 1, 1, tzinfo=timezone.utc)

    class FakeDatetime:
        @classmethod
        def now(
            cls, tz: timezone | None = None
        ) -> datetime:  # pragma: no cover - signature helper
            assert tz is timezone.utc
            return fixed

    monkeypatch.setattr("twitch_subs.application.watcher.datetime", FakeDatetime)

    repo = InMemoryStateRepo()
    notifier = DummyNotifier()
    user = UserRecord("1", "foo", "Foo", BroadcasterType.PARTNER)
    event_bus = InMemoryEventBus()

    async def forward_change(event: UserBecomeSubscribtable) -> None:
        await notifier.notify_about_change(
            LoginStatus(event.login, event.current_state, None), event.current_state
        )

    event_bus.subscribe(UserBecomeSubscribtable, forward_change)
    watcher = Watcher(DummyTwitch({"foo": user}), notifier, repo, event_bus)

    stop = asyncio.Event()
    changed = await watcher.run_once(["foo"], stop)
    assert changed is True

    stored = repo.get_sub_state("foo")
    assert stored is not None
    assert stored.is_subscribed is True
    assert stored.tier == BroadcasterType.PARTNER.value
    assert stored.since == fixed


@pytest.mark.asyncio
async def test_run_once_preserves_since(monkeypatch: pytest.MonkeyPatch) -> None:
    earlier = datetime(2023, 5, 4, tzinfo=timezone.utc)
    repo = InMemoryStateRepo(
        [
            SubState(
                login="foo",
                is_subscribed=True,
                tier=BroadcasterType.AFFILIATE.value,
                since=earlier,
            )
        ]
    )
    notifier = DummyNotifier()
    user = UserRecord("1", "foo", "Foo", BroadcasterType.AFFILIATE)
    event_bus = InMemoryEventBus()
    watcher = Watcher(DummyTwitch({"foo": user}), notifier, repo, event_bus)

    stop = asyncio.Event()
    changed = await watcher.run_once(["foo"], stop)
    assert changed is False
    # ensure no new notification and since preserved
    # FIX: AGA
    # a9sert not any(
    #     isinstance(evt, UserBecomeSubscribtable) for evt in event_bus.mem.items()
    # )
    # assert any(isinstance(evt, OnceChecked) for evt in event_bus.mem.items())
    # assert any(isinstance(evt, LoopChecked) for evt in event_bus.mem.items())
    assert repo.get_sub_state("foo").since == earlier


@pytest.mark.asyncio
async def test_run_once_stop_event_short_circuits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stop = asyncio.Event()

    async def delayed_user(login: str) -> UserRecord | None:
        if login == "foo":
            stop.set()
            return UserRecord("1", "foo", "Foo", BroadcasterType.AFFILIATE)
        return None

    class StopTwitch(TwitchClientProtocol):
        async def get_user_by_login(self, login: str) -> UserRecord | None:
            return await delayed_user(login)

    repo = InMemoryStateRepo()
    watcher = Watcher(StopTwitch(), DummyNotifier(), repo, InMemoryEventBus())

    changed = await watcher.run_once(["foo", "bar"], stop)
    assert changed is False
    assert repo.set_many_calls == []


@pytest.mark.asyncio
async def test_watch_loop_counts_and_reports(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = InMemoryStateRepo()
    notifier = DummyNotifier()
    event_bus = InMemoryEventBus()
    watcher = Watcher(DummyTwitch({}), notifier, repo, event_bus)
    logins = StaticLogins(["foo"])
    stop = asyncio.Event()

    call_counter = {"calls": 0}

    async def fake_run_once(_: list[str], __: asyncio.Event) -> bool:
        call_counter["calls"] += 1
        if call_counter["calls"] == 2:
            raise RuntimeError("boom")
        await event_bus.publish(LoopChecked(logins=("foo",)))
        return True

    published: list[tuple[str, Sequence[str]]] = []

    async def on_loop_failed(event: LoopCheckFailed) -> None:
        published.append(("failed", tuple(event.logins)))

    async def on_loop_checked(event: LoopChecked) -> None:
        published.append(("checked", tuple(event.logins)))

    event_bus.subscribe(LoopCheckFailed, on_loop_failed)
    event_bus.subscribe(LoopChecked, on_loop_checked)

    monkeypatch.setattr(watcher, "run_once", fake_run_once)

    async def fake_wait_for(awaitable: asyncio.Future, timeout: float) -> None:
        task = asyncio.create_task(awaitable)
        await asyncio.sleep(0)
        if call_counter["calls"] >= 3:
            stop.set()
            return await task
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        raise TimeoutError

    monkeypatch.setattr(
        "twitch_subs.application.watcher.asyncio.wait_for", fake_wait_for
    )

    await watcher.watch(logins, interval=0, stop_event=stop)

    assert notifier.start_called and notifier.stop_called
    # run_once called three times: two successful attempts + one after failure before stop
    assert call_counter["calls"] >= 3
