from twitch_subs.domain.models import BroadcasterType, LoginStatus, UserRecord
from twitch_subs.domain.ports import NotifierProtocol, TwitchClientProtocol


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
