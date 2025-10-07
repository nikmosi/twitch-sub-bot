from __future__ import annotations

from dataclasses import dataclass

import pytest

from twitch_subs.config import Settings
from twitch_subs.container import Container


@dataclass
class FakeNotifier:
    bot: object
    chat_id: str

    async def notify_about_start(self) -> None:  # pragma: no cover - not used
        raise AssertionError("should not be called in test")

    async def aclose(self) -> None:
        await self.bot.session.close()


class FakeBot:
    def __init__(self, token: str, default: object | None = None) -> None:
        self.token = token
        self.default = default
        self.session = FakeSession()


class FakeSession:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class FakeTwitch:
    def __init__(self, client_id: str, client_secret: str) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.closed = False

    @classmethod
    def from_creds(cls, creds) -> "FakeTwitch":
        return cls(creds.client_id, creds.client_secret)

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("TWITCH_CLIENT_ID", "id")
    monkeypatch.setenv("TWITCH_CLIENT_SECRET", "secret")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
    monkeypatch.setenv("DB_URL", "sqlite:///:memory:")
    monkeypatch.setenv("DB_ECHO", "0")
    return Settings()


def test_container_singletons(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    monkeypatch.setattr("twitch_subs.container.Bot", FakeBot)
    monkeypatch.setattr("twitch_subs.container.TelegramNotifier", FakeNotifier)
    monkeypatch.setattr("twitch_subs.container.TwitchClient", FakeTwitch)

    container = Container(settings)

    engine1 = container.engine
    engine2 = container.engine
    assert engine1 is engine2

    repo1 = container.watchlist_repo
    repo2 = container.watchlist_repo
    assert repo1 is repo2

    sub1 = container.sub_state_repo
    sub2 = container.sub_state_repo
    assert sub1 is sub2

    bot1 = container.telegram_bot
    bot2 = container.telegram_bot
    assert bot1 is bot2

    notifier1 = container.notifier
    notifier2 = container.notifier
    assert notifier1 is notifier2
    assert notifier1.bot is bot1
    assert container.build_watcher().twitch.client_id == "id"

    watchlist_bot = container.build_bot()
    assert watchlist_bot.bot is bot1
    assert watchlist_bot.service.repo is repo1


@pytest.mark.asyncio
async def test_container_aclose(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> None:
    monkeypatch.setattr("twitch_subs.container.Bot", FakeBot)
    monkeypatch.setattr("twitch_subs.container.TelegramNotifier", FakeNotifier)
    monkeypatch.setattr("twitch_subs.container.TwitchClient", FakeTwitch)

    container = Container(settings)
    notifier = container.notifier
    twitch = container.twitch_client
    _ = container.engine

    await container.aclose()

    assert notifier.bot.session.closed
    assert container._telegram_bot is None
    assert container._notifier is None
    assert container._engine is None
    assert container._twitch is None
    assert container._watchlist_repo is None
    assert container._sub_state_repo is None
    # ensure original instance got closed
    assert isinstance(twitch, FakeTwitch)
    assert twitch.closed
