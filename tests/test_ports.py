from twitch_subs.domain.models import BroadcasterType, UserRecord
from twitch_subs.domain.ports import (
    NotifierProtocol,
    StateRepositoryProtocol,
    TwitchClientProtocol,
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


def test_state_repository_protocol_subclass() -> None:
    class Impl(StateRepositoryProtocol):
        def __init__(self) -> None:  # noqa: D401
            self.saved: dict[str, BroadcasterType] | None = None

        def load(self) -> dict[str, BroadcasterType]:  # noqa: D401
            return {}

        def save(self, state: dict[str, BroadcasterType]) -> None:  # noqa: D401
            self.saved = state

    impl = Impl()
    assert impl.load() == {}
    impl.save({"foo": BroadcasterType.NONE})
    assert impl.saved == {"foo": BroadcasterType.NONE}
