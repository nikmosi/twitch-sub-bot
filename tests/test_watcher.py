import threading
import time
from typing import Dict, Sequence

import pytest

from twitch_subs.application.logins import LoginsProvider
from twitch_subs.application.watcher import Watcher
from twitch_subs.domain.models import BroadcasterType, LoginStatus, UserRecord
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
        self.data: Dict[str, BroadcasterType] = {}

    def load(self) -> Dict[str, BroadcasterType]:
        return self.data

    def save(self, state: Dict[str, BroadcasterType]) -> None:
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
    assert rows[1].login == "bar" and rows[1].broadcaster_type is None


def test_run_once_updates_state_and_notifies() -> None:
    users: dict[str, UserRecord | None] = {
        "foo": UserRecord("1", "foo", "Foo", BroadcasterType.AFFILIATE),
    }
    twitch = DummyTwitch(users)
    notifier = DummyNotifier()
    state_repo = DummyState()
    watcher = Watcher(twitch, notifier, state_repo)

    state: Dict[str, BroadcasterType] = {}
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

    state: Dict[str, BroadcasterType] = {"foo": BroadcasterType.AFFILIATE}
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

    def fake_run_once(
        self: Watcher, logins: list[str], state: dict[str, BroadcasterType]
    ) -> bool:  # noqa: D401
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
