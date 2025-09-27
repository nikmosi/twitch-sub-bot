import asyncio
import threading
import time
from pathlib import Path

from twitch_subs.application.logins import LoginsProvider
from twitch_subs.application.watcher import Watcher
from twitch_subs.domain.models import BroadcasterType, LoginStatus, UserRecord
from twitch_subs.domain.ports import NotifierProtocol, TwitchClientProtocol
from twitch_subs.infrastructure.repository_sqlite import (
    SqliteSubscriptionStateRepository,
)


class DummyNotifier(NotifierProtocol):
    def __init__(self) -> None:
        self.change_called = False
        self.report_args: tuple | None = None

    def notify_about_change(self, status: LoginStatus, curr: BroadcasterType) -> None:  # noqa: D401
        _ = status
        _ = curr
        self.change_called = True

    def notify_about_start(self) -> None:  # noqa: D401
        pass

    def notify_report(self, logins, state, checks, errors) -> None:  # noqa: D401
        self.report_args = (list(logins), state, checks, errors)

    def send_message(
        self, text, disable_web_page_preview=True, disable_notification=False
    ):  # noqa: D401
        _ = text
        _ = disable_web_page_preview
        _ = disable_notification


class DummyTwitch(TwitchClientProtocol):
    def __init__(self, users: dict[str, UserRecord | None]):
        self.users = users

    async def get_user_by_login(self, login: str) -> UserRecord | None:  # noqa: D401
        return self.users.get(login)


def test_run_once_persists_state_and_notifies(tmp_path: Path) -> None:
    db = tmp_path / "s.db"
    repo = SqliteSubscriptionStateRepository(f"sqlite:///{db}")
    twitch = DummyTwitch(
        {"foo": UserRecord("1", "foo", "Foo", BroadcasterType.AFFILIATE)}
    )
    notifier = DummyNotifier()
    watcher = Watcher(twitch, notifier, repo)
    assert asyncio.run(watcher.run_once(["foo"])) is True
    st = repo.get_sub_state("foo")
    assert st and st.is_subscribed
    assert notifier.change_called


def test_run_once_idempotent(tmp_path: Path) -> None:
    db = tmp_path / "id.db"
    repo = SqliteSubscriptionStateRepository(f"sqlite:///{db}")
    twitch = DummyTwitch(
        {"foo": UserRecord("1", "foo", "Foo", BroadcasterType.AFFILIATE)}
    )
    notifier = DummyNotifier()
    watcher = Watcher(twitch, notifier, repo)
    asyncio.run(watcher.run_once(["foo"]))
    count1 = len(repo.list_all())
    asyncio.run(watcher.run_once(["foo"]))
    count2 = len(repo.list_all())
    assert count1 == count2 == 1


def test_run_once_no_change(tmp_path: Path) -> None:
    db = tmp_path / "nc.db"
    repo = SqliteSubscriptionStateRepository(f"sqlite:///{db}")
    twitch = DummyTwitch(
        {"foo": UserRecord("1", "foo", "Foo", BroadcasterType.AFFILIATE)}
    )
    notifier = DummyNotifier()
    watcher = Watcher(twitch, notifier, repo)
    asyncio.run(watcher.run_once(["foo"]))
    notifier.change_called = False
    assert asyncio.run(watcher.run_once(["foo"])) is False
    assert notifier.change_called is False


def test_watcher_reports(tmp_path: Path) -> None:
    db = tmp_path / "r.db"
    repo = SqliteSubscriptionStateRepository(f"sqlite:///{db}")
    twitch = DummyTwitch({})
    notifier = DummyNotifier()
    watcher = Watcher(twitch, notifier, repo)

    class DummyLogins(LoginsProvider):
        def get(self) -> list[str]:  # noqa: D401
            return []

    stop = threading.Event()

    def fake_wait(timeout: float) -> bool:  # noqa: D401
        stop.set()
        return True

    stop.wait = fake_wait  # type: ignore[assignment]
    orig = time.time
    time.time = lambda: 0.0  # type: ignore
    try:
        asyncio.run(watcher.watch(DummyLogins(), 0, stop, report_interval=0))
    finally:
        time.time = orig  # type: ignore
    assert notifier.report_args == ([], {}, 1, 0)
