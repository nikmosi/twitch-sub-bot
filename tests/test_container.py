from __future__ import annotations

from dataclasses import dataclass
import inspect

import pytest
from aiogram.client.session.aiohttp import AiohttpSession
from dependency_injector import providers

from twitch_subs.config import Settings
from twitch_subs.container import AppContainer, build_container, shutdown_container


@dataclass
class FakeNotifier:
    bot: object
    chat_id: str


class FakeBot:
    def __init__(
        self, token: str, session: AiohttpSession, default: object | None = None
    ) -> None:
        self.token = token
        self.session = session
        self.default = default

    async def close(self) -> None:  # pragma: no cover - not used in test
        await self.session.close()


class FakeTwitch:
    def __init__(self, client_id: str, client_secret: str) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.closed = False

    @classmethod
    def from_creds(cls, creds) -> "FakeTwitch":
        return cls(creds.client_id, creds.client_secret)

    async def aclose(self) -> None:
        self.closed = True


class FakeSession:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class FakeDayChangeScheduler:
    def __init__(self, event_bus, cron: str) -> None:
        self.event_bus = event_bus
        self.cron = cron
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("TWITCH_CLIENT_ID", "id")
    monkeypatch.setenv("TWITCH_CLIENT_SECRET", "secret")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
    monkeypatch.setenv("DB_URL", "sqlite:///:memory:")
    monkeypatch.setenv("DB_ECHO", "0")
    return Settings()


@pytest.mark.asyncio
async def test_build_container_initializes_resources(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    monkeypatch.setattr("twitch_subs.container.Bot", FakeBot)
    monkeypatch.setattr("twitch_subs.container.TelegramNotifier", FakeNotifier)
    monkeypatch.setattr("twitch_subs.container.TwitchClient", FakeTwitch)
    monkeypatch.setattr("twitch_subs.container.AiohttpSession", FakeSession)
    monkeypatch.setattr(
        "twitch_subs.container.DayChangeScheduler", FakeDayChangeScheduler
    )

    container: AppContainer = await build_container(settings)

    engine1 = container.engine()
    engine2 = container.engine()
    assert engine1 is engine2

    repo1 = container.watchlist_repo()
    repo2 = container.watchlist_repo()
    assert repo1 is repo2

    sub_state1 = container.sub_state_repo()
    sub_state2 = container.sub_state_repo()
    assert sub_state1 is sub_state2

    session = container.tg_session()
    if inspect.isawaitable(session):
        session = await session
    bot = container.telegram_bot()
    if inspect.isawaitable(bot):
        bot = await bot
    assert bot.session is session

    container.notifier.override(providers.Object(FakeNotifier(bot, "123")))

    notifier1 = container.notifier()
    notifier2 = container.notifier()
    assert notifier1 is notifier2
    assert notifier1.bot is bot

    twitch = container.twitch_client()
    if inspect.isawaitable(twitch):
        twitch = await twitch
    watcher = container.watcher()
    if inspect.isawaitable(watcher):
        watcher = await watcher
    assert watcher.twitch is twitch
    assert watcher.notifier is notifier1

    bot_app = container.bot_app()
    if inspect.isawaitable(bot_app):
        bot_app = await bot_app
    assert bot_app.bot is bot
    assert bot_app.service.repo is repo1

    scheduler = container.day_scheduler()
    if inspect.isawaitable(scheduler):
        scheduler = await scheduler
    assert isinstance(scheduler, FakeDayChangeScheduler)
    assert scheduler.started

    await shutdown_container(container)

    assert session.closed
    assert twitch.closed
    assert scheduler.stopped
