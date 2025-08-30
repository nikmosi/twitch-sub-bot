import threading
import time
from typing import Any, Sequence

import pytest

from twitch_subs.application.logins import LoginsProvider
from twitch_subs.application.watcher import Watcher
from twitch_subs.domain.models import BroadcasterType, LoginStatus, State, UserRecord
from twitch_subs.domain.ports import (
    NotifierProtocol,
    StateRepositoryProtocol,
    TwitchClientProtocol,
)


class DummyNotifier(NotifierProtocol):
    def __init__(self) -> None:
        self.sent: list[tuple[str, bool]] = []
        self.notify_about_start_check = False
        self.notify_about_change_check = False
        self.notify_report_check = False

    def notify_about_start(self) -> None:
        self.notify_about_start_check = True

    def notify_about_change(self, status: LoginStatus, curr: BroadcasterType) -> None:
        self.notify_about_change_check = True

    def notify_report(
        self,
        logins: Sequence[str],
        state: dict[str, BroadcasterType],
        checks: int,
        errors: int,
    ) -> None:
        self.notify_report_check = True

    def send_message(
        self,
        text: str,
        disable_web_page_preview: bool = True,
        disable_notification: bool = False,
    ) -> None:
        _ = disable_web_page_preview
        self.sent.append((text, disable_notification))


class DummyTwitch(TwitchClientProtocol):
    def __init__(self, users: dict[str, UserRecord | None]):
        self.users = users

    def get_user_by_login(self, login: str) -> UserRecord | None:
        return self.users.get(login)


class DummyState(StateRepositoryProtocol):
    def __init__(self) -> None:
        self.data = State()

    def load(self) -> State:
        return self.data

    def save(self, state: State) -> None:
        self.data = state


def test_check_logins() -> None:
    users = {
        "foo": UserRecord("1", "foo", "Foo", BroadcasterType.AFFILIATE),
        "bar": None,
    }
    twitch = DummyTwitch(users)
    notifier = DummyNotifier()
    state_repo = DummyState()
    watcher = Watcher(twitch, notifier, state_repo)

    rows = [watcher.check_login(i) for i in ["foo", "bar"]]
    assert (
        rows[0].login == "foo" and rows[0].broadcaster_type == BroadcasterType.AFFILIATE
    )
    assert rows[1].login == "bar" and rows[1].broadcaster_type is BroadcasterType.NONE


def test_run_once_updates_state_and_notifies() -> None:
    users: dict[str, UserRecord | None] = {
        "foo": UserRecord("1", "foo", "Foo", BroadcasterType.AFFILIATE),
    }
    twitch = DummyTwitch(users)
    notifier = DummyNotifier()
    state_repo = DummyState()
    watcher = Watcher(twitch, notifier, state_repo)

    state = State()
    changed = watcher.run_once(["foo"], state)

    assert changed is True
    assert state["foo"] == BroadcasterType.AFFILIATE
    assert notifier.notify_about_change_check


def test_run_once_no_change_does_not_notify() -> None:
    users: dict[str, UserRecord | None] = {
        "foo": UserRecord("1", "foo", "Foo", BroadcasterType.AFFILIATE)
    }
    twitch = DummyTwitch(users)
    notifier = DummyNotifier()
    state_repo = DummyState()
    watcher = Watcher(twitch, notifier, state_repo)

    state = State({"foo": BroadcasterType.AFFILIATE})
    changed = watcher.run_once(["foo"], state)

    assert changed is False
    assert not notifier.sent


def test_watcher_stops_quickly_on_event() -> None:
    twitch = DummyTwitch({})
    notifier = DummyNotifier()
    state_repo = DummyState()
    watcher = Watcher(twitch, notifier, state_repo)

    class DummyLogins(LoginsProvider):
        def get(self) -> list[str]:  # noqa: D401
            return ["foo"]

    stop = threading.Event()
    thread = threading.Thread(target=watcher.watch, args=(DummyLogins(), 1, stop))
    thread.start()
    time.sleep(0.1)
    stop.set()
    thread.join(1)
    assert not thread.is_alive()


def test_watcher_no_work_after_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    twitch = DummyTwitch({})
    notifier = DummyNotifier()
    state_repo = DummyState()
    watcher = Watcher(twitch, notifier, state_repo)

    calls = {"count": 0}

    def fake_run_once(self: Watcher, logins: list[str], state: State) -> bool:  # noqa: D401
        _ = self
        _ = logins
        _ = state
        calls["count"] += 1
        stop.set()
        return False

    monkeypatch.setattr(Watcher, "run_once", fake_run_once, raising=False)

    class DummyLogins(LoginsProvider):
        def get(self) -> list[str]:  # noqa: D401
            return ["foo"]

    stop = threading.Event()
    thread = threading.Thread(target=watcher.watch, args=(DummyLogins(), 1, stop))
    thread.start()
    thread.join(1)
    assert calls["count"] == 1


def test_watch_respects_interval(monkeypatch: pytest.MonkeyPatch) -> None:
    twitch = DummyTwitch({})
    notifier = DummyNotifier()
    state_repo = DummyState()
    watcher = Watcher(twitch, notifier, state_repo)

    class DummyLogins(LoginsProvider):
        def get(self) -> list[str]:  # noqa: D401
            return ["foo"]

    stop = threading.Event()
    waits: list[float] = []

    def fake_wait(timeout: float) -> bool:
        waits.append(timeout)
        stop.set()
        return True

    monkeypatch.setattr(stop, "wait", fake_wait)
    watcher.watch(DummyLogins(), 5, stop)
    assert waits == [5]


def test_watch_immediate_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    twitch = DummyTwitch({})
    notifier = DummyNotifier()
    state_repo = DummyState()
    watcher = Watcher(twitch, notifier, state_repo)

    class DummyLogins(LoginsProvider):
        def get(self) -> list[str]:  # noqa: D401
            return ["foo"]

    stop = threading.Event()
    stop.set()

    called = False

    def fake_run_once(self: Any, logins: Any, state: Any):  # type: ignore[override]
        nonlocal called
        called = True
        return False

    monkeypatch.setattr(Watcher, "run_once", fake_run_once, raising=False)
    watcher.watch(DummyLogins(), 5, stop)
    assert called is False


def test_watch_reports(monkeypatch: pytest.MonkeyPatch) -> None:
    twitch = DummyTwitch({})
    notifier = DummyNotifier()
    state_repo = DummyState()
    watcher = Watcher(twitch, notifier, state_repo)

    class DummyLogins(LoginsProvider):
        def get(self) -> list[str]:  # noqa: D401
            return []

    stop = threading.Event()

    def fake_wait(timeout: float) -> bool:
        stop.set()
        return True

    monkeypatch.setattr(stop, "wait", fake_wait)
    monkeypatch.setattr(time, "time", lambda: 0.0)

    called = {}

    def fake_notify_report(
        self: Any,
        logins: Sequence[str],
        state: dict[str, BroadcasterType],
        checks: int,
        errors: int,
    ) -> None:
        called["reported"] = (logins, checks, errors)

    monkeypatch.setattr(
        DummyNotifier, "notify_report", fake_notify_report, raising=False
    )
    watcher.watch(DummyLogins(), 0, stop, report_interval=0)
    assert called["reported"] == ([], 1, 0)
