import pytest

from collections.abc import Iterable


from twitch_subs.domain.models import SubState, UserRecord
from twitch_subs.domain.ports import (
    NotifierProtocol,
    SubscriptionStateRepo,
    TwitchClientProtocol,
    WatchlistRepository,
)


def test_twitch_client_protocol_subclass() -> None:
    class Impl(TwitchClientProtocol):
        def get_user_by_login(self, login: str) -> UserRecord | None:  # noqa: D401
            _ = login
            return None

    impl = Impl()
    assert impl.get_user_by_login("foo") is None


def test_notifier_protocol_subclass() -> None:
    class Impl(NotifierProtocol):
        def __init__(self) -> None:  # noqa: D401
            self.sent: list[tuple[str, bool, bool]] = []

        def send_message(
            self,
            text: str,
            disable_web_page_preview: bool = True,
            disable_notification: bool = False,
        ) -> None:  # noqa: D401
            self.sent.append((text, disable_web_page_preview, disable_notification))

    impl = Impl()
    impl.send_message("hi", False, True)
    assert impl.sent == [("hi", False, True)]


@pytest.mark.parametrize("name", ["foo", "bar"])
def test_watchlist_repo_protocol_param(name: str) -> None:
    class Impl(WatchlistRepository):
        def __init__(self) -> None:  # noqa: D401
            self.data: list[str] = []

        def add(self, login: str) -> None:  # noqa: D401
            self.data.append(login)

        def remove(self, login: str) -> bool:  # noqa: D401
            try:
                self.data.remove(login)
                return True
            except ValueError:
                return False

        def list(self) -> list[str]:  # noqa: D401
            return sorted(self.data)

        def exists(self, login: str) -> bool:  # noqa: D401
            return login in self.data

    repo = Impl()
    repo.add(name)
    assert repo.exists(name)


def test_subscription_state_repo_protocol_subclass() -> None:
    class Impl(SubscriptionStateRepo):
        def __init__(self) -> None:  # noqa: D401
            self.data: dict[str, SubState] = {}

        def get_sub_state(self, login: str) -> SubState | None:  # noqa: D401
            return self.data.get(login)

        def upsert_sub_state(self, state: SubState) -> None:  # noqa: D401
            self.data[state.login] = state

        def set_many(self, states: Iterable[SubState]) -> None:  # noqa: D401
            for st in states:
                self.data[st.login] = st

    repo = Impl()
    st = SubState("foo", True)
    repo.upsert_sub_state(st)
    assert repo.get_sub_state("foo") == st


def test_watchlist_repository_protocol_subclass() -> None:
    class Impl(WatchlistRepository):
        def __init__(self) -> None:
            self.data: list[str] = []

        def add(self, login: str) -> None:  # noqa: D401
            if login not in self.data:
                self.data.append(login)

        def remove(self, login: str) -> bool:  # noqa: D401
            try:
                self.data.remove(login)
                return True
            except ValueError:
                return False

        def list(self) -> list[str]:  # noqa: D401
            return sorted(self.data)

        def exists(self, login: str) -> bool:  # noqa: D401
            return login in self.data

    impl = Impl()
    impl.add("foo")
    assert impl.exists("foo")
    assert impl.list() == ["foo"]
    assert impl.remove("foo") is True
