import asyncio
import contextlib
from collections import deque
from dataclasses import replace
from datetime import datetime, timezone
from typing import Iterable

import pytest

from twitch_subs.application.logins import LoginsProvider
from twitch_subs.application.watcher import Watcher
from twitch_subs.domain.models import (
    BroadcasterType,
    LoginStatus,
    State,
    SubState,
    UserRecord,
)
from twitch_subs.domain.ports import NotifierProtocol, SubscriptionStateRepo, TwitchClientProtocol


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
        self.reports: list[tuple[list[str], dict[str, BroadcasterType], int, int]] = []
        self.messages: list[str] = []

    async def notify_about_change(self, status: LoginStatus, curr: BroadcasterType) -> None:
        self.changes.append((status, curr))

    async def notify_about_start(self) -> None:
        self.start_called = True

    async def notify_about_stop(self) -> None:
        self.stop_called = True

    async def notify_report(
        self, logins: Iterable[str], state: dict[str, BroadcasterType], checks: int, errors: int
    ) -> None:
        self.reports.append((list(logins), state, checks, errors))

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


@pytest.mark.asyncio
async def test_check_login_found_and_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    user = UserRecord("1", "foo", "Foo", BroadcasterType.AFFILIATE)
    twitch = DummyTwitch({"foo": user, "bar": None})
    watcher = Watcher(twitch, DummyNotifier(), InMemoryStateRepo())

    status = await watcher.check_login("foo")
    assert status.user == user
    assert status.broadcaster_type is BroadcasterType.AFFILIATE

    missing = await watcher.check_login("bar")
    assert missing.user is None
    assert missing.broadcaster_type is BroadcasterType.NONE


@pytest.mark.asyncio
async def test_run_once_transitions_and_notifies(monkeypatch: pytest.MonkeyPatch) -> None:
    fixed = datetime(2024, 1, 1, tzinfo=timezone.utc)

    class FakeDatetime:
        @classmethod
        def now(cls, tz: timezone | None = None) -> datetime:  # pragma: no cover - signature helper
            assert tz is timezone.utc
            return fixed

    monkeypatch.setattr("twitch_subs.application.watcher.datetime", FakeDatetime)

    repo = InMemoryStateRepo()
    notifier = DummyNotifier()
    user = UserRecord("1", "foo", "Foo", BroadcasterType.PARTNER)
    watcher = Watcher(DummyTwitch({"foo": user}), notifier, repo)

    stop = asyncio.Event()
    changed = await watcher.run_once(["foo"], stop)
    assert changed is True
    assert notifier.changes and notifier.changes[0][0].login == "foo"
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
    watcher = Watcher(DummyTwitch({"foo": user}), notifier, repo)

    stop = asyncio.Event()
    changed = await watcher.run_once(["foo"], stop)
    assert changed is False
    # ensure no new notification and since preserved
    assert notifier.changes == []
    assert repo.get_sub_state("foo").since == earlier


@pytest.mark.asyncio
async def test_run_once_stop_event_short_circuits(monkeypatch: pytest.MonkeyPatch) -> None:
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
    watcher = Watcher(StopTwitch(), DummyNotifier(), repo)

    changed = await watcher.run_once(["foo", "bar"], stop)
    assert changed is False
    assert repo.set_many_calls == []


@pytest.mark.asyncio
async def test_report_aggregates_state() -> None:
    repo = InMemoryStateRepo(
        [
            SubState("foo", True, BroadcasterType.AFFILIATE.value, since=None),
            SubState("bar", False, None, since=None),
        ]
    )
    notifier = DummyNotifier()
    watcher = Watcher(DummyTwitch({}), notifier, repo)

    await watcher._report(["foo", "bar"], checks=3, errors=1)
    assert notifier.reports == [
        (
            ["foo", "bar"],
            {"foo": BroadcasterType.AFFILIATE, "bar": BroadcasterType.NONE},
            3,
            1,
        )
    ]


@pytest.mark.asyncio
async def test_watch_loop_counts_and_reports(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = InMemoryStateRepo()
    notifier = DummyNotifier()
    watcher = Watcher(DummyTwitch({}), notifier, repo)
    logins = StaticLogins(["foo"])
    stop = asyncio.Event()

    call_counter = {"calls": 0}

    async def fake_run_once(_: list[str], __: asyncio.Event) -> bool:
        call_counter["calls"] += 1
        if call_counter["calls"] == 2:
            raise RuntimeError("boom")
        return True

    async def fake_report(logins_arg: list[str], checks: int, errors: int) -> None:
        notifier.reports.append((logins_arg, {}, checks, errors))

    monkeypatch.setattr(watcher, "run_once", fake_run_once)
    monkeypatch.setattr(watcher, "_report", fake_report)

    times = iter([0.0, 1.0, 6.0, 7.0])
    monkeypatch.setattr("twitch_subs.application.watcher.time.time", lambda: next(times))

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

    monkeypatch.setattr("twitch_subs.application.watcher.asyncio.wait_for", fake_wait_for)

    await watcher.watch(logins, interval=0, stop_event=stop, report_interval=5)

    assert notifier.start_called and notifier.stop_called
    # run_once called three times: two successful attempts + one after report before stop
    assert call_counter["calls"] >= 3
    # report called once with checks reset after error handling
    assert notifier.reports[0][2:] == (2, 1)


def test_state_copy_roundtrip() -> None:
    state = State({"foo": BroadcasterType.AFFILIATE})
    cloned = state.copy()
    assert cloned is not state
    assert dict(cloned) == {"foo": BroadcasterType.AFFILIATE}

