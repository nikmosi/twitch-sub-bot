from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
import inspect

import pytest
from aiogram.client.session.aiohttp import AiohttpSession
from dependency_injector import providers

from twitch_subs.config import Settings
from twitch_subs.container import AppContainer, shutdown_container
from twitch_subs.application.watcher import Watcher


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


class FakeConnection:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class FakeEventBus:
    def __init__(self, *args, **kwargs) -> None:
        self.started = False
        self.stopped = False
        self.connection = kwargs.get("connection")

    async def __aenter__(self) -> "FakeEventBus":
        self.started = True
        return self

    async def __aexit__(self, *_: object) -> None:
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
    monkeypatch.setattr("twitch_subs.container.RabbitMQEventBus", FakeEventBus)

    connections: list[FakeConnection] = []

    @asynccontextmanager
    async def fake_rabbitmq_resource(url: str | None = None):
        conn = FakeConnection()
        connections.append(conn)
        try:
            yield conn
        finally:
            await conn.close()

    monkeypatch.setattr(
        "twitch_subs.container._rabbitmq_resource", fake_rabbitmq_resource
    )

    async def fake_build_container(settings: Settings) -> AppContainer:
        container = AppContainer()
        container.container_config.from_pydantic(settings)
        container.rabbit_conn.override(providers.Resource(fake_rabbitmq_resource))
        await container.init_resources()
        return container

    container: AppContainer = await fake_build_container(settings)

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
    if inspect.isawaitable(notifier1):
        notifier1 = await notifier1
    if inspect.isawaitable(notifier2):
        notifier2 = await notifier2
    assert notifier1 is notifier2
    assert notifier1.bot is bot

    twitch = container.twitch_client()
    if inspect.isawaitable(twitch):
        twitch = await twitch
    container.watcher.override(
        providers.Object(Watcher(twitch, notifier1, sub_state1, FakeEventBus()))
    )
    watcher = container.watcher()
    if inspect.isawaitable(watcher):
        watcher = await watcher
    assert watcher.twitch is twitch
    assert watcher.notifier is notifier1

    bot_cm = container.bot_app()
    if inspect.isawaitable(bot_cm):
        bot_cm = await bot_cm
    async with bot_cm as bot_app:
        assert bot_app.bot is bot
        assert bot_app.service.repo is repo1

    await shutdown_container(container)

    assert session.closed
    assert twitch.closed
    assert connections and connections[0].closed
