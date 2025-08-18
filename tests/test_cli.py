from typing import Any

from twitch_subs import cli


def test_cli_watch_invokes_watcher(monkeypatch) -> None:
    # Set required environment variables
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    monkeypatch.setenv("TWITCH_CLIENT_ID", "id")
    monkeypatch.setenv("TWITCH_CLIENT_SECRET", "secret")

    # Avoid loading actual .env file
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)

    # Provide fake implementations for dependencies
    class DummyTwitch:
        @classmethod
        def from_creds(cls, creds):  # noqa: D401
            return cls()

    class DummyNotifier:
        def __init__(self, token: str, chat_id: str) -> None:  # noqa: D401
            self.token = token
            self.chat_id = chat_id

        def send_message(self, text: str, disable_web_page_preview: bool = True) -> None:  # noqa: D401
            pass

    class DummyStateRepo:
        def load(self) -> dict[str, Any]:  # noqa: D401
            return {}

        def save(self, state: dict[str, Any]) -> None:  # noqa: D401
            pass

    monkeypatch.setattr(cli, "TwitchClient", DummyTwitch)
    monkeypatch.setattr(cli, "TelegramNotifier", DummyNotifier)
    monkeypatch.setattr(cli, "StateRepository", lambda: DummyStateRepo())

    calls: dict[str, Any] = {}

    def fake_watch(self, logins, interval, stop_event=None):  # noqa: D401
        calls["logins"] = logins
        calls["interval"] = interval

    monkeypatch.setattr(cli.Watcher, "watch", fake_watch, raising=False)

    assert cli.main(["watch", "foo", "foo", "bar", "--interval", "1"]) == 0
    assert calls["logins"] == ["foo", "bar"]  # duplicates removed
    assert calls["interval"] == 1
