from typing import Dict

from twitch_subs.application.watcher import Watcher
from twitch_subs.domain.models import BroadcasterType, UserRecord
from twitch_subs.infrastructure.state import StateRepository
from twitch_subs.infrastructure.telegram import TelegramNotifier


class DummyNotifier(TelegramNotifier):
    def __init__(self) -> None:  # type: ignore[override]
        self.sent: list[str] = []

    def send_message(self, text: str, disable_web_page_preview: bool = True) -> None:  # type: ignore[override]
        self.sent.append(text)


class DummyTwitch:
    def __init__(self, users: Dict[str, UserRecord | None]):
        self.users = users

    def get_user_by_login(self, login: str) -> UserRecord | None:
        return self.users.get(login)


class DummyState(StateRepository):
    def __init__(self) -> None:
        self.data: Dict[str, BroadcasterType] = {}

    def load(self) -> Dict[str, BroadcasterType]:  # type: ignore[override]
        return self.data

    def save(self, state: Dict[str, BroadcasterType]) -> None:  # type: ignore[override]
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

    rows = watcher.check_logins(["foo", "bar"])
    assert rows[0].login == "foo" and rows[0].broadcaster_type == BroadcasterType.AFFILIATE
    assert rows[1].login == "bar" and rows[1].broadcaster_type is None


def test_run_once_updates_state_and_notifies() -> None:
    users = {
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
    assert notifier.sent
