# container_di.py
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, contextmanager
from typing import AsyncIterator, Awaitable, Iterator

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from dependency_injector import containers, providers
from sqlalchemy import Engine, create_engine, text

from twitch_subs.application.ports import (
    EventBus,
    NotifierProtocol,
)
from twitch_subs.application.reporting import DayChangeScheduler
from twitch_subs.application.watchlist_service import WatchlistService
from twitch_subs.domain.models import TwitchAppCreds
from twitch_subs.infrastructure.event_bus import InMemoryEventBus, RabbitMQEventBus
from twitch_subs.infrastructure.repository_sqlite import (
    SqliteSubscriptionStateRepository,
    SqliteWatchlistRepository,
    metadata,
)
from twitch_subs.infrastructure.telegram import TelegramNotifier, TelegramWatchlistBot
from twitch_subs.infrastructure.twitch import TwitchClient

from .application.watcher import Watcher
from .config import Settings

# ---------- low-level resources ----------


@contextmanager
def _engine_resource(database_url: str, echo: bool) -> Iterator[Engine]:
    engine = create_engine(database_url, echo=echo, future=True)
    with engine.begin() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL"))
    metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@asynccontextmanager
async def _aiohttp_session_resource() -> AsyncIterator[AiohttpSession]:
    session = AiohttpSession()
    try:
        yield session
    finally:
        await session.close()


@asynccontextmanager
async def _twitch_client_resource(creds: TwitchAppCreds) -> AsyncIterator[TwitchClient]:
    client = TwitchClient.from_creds(creds)
    try:
        yield client
    finally:
        await client.aclose()


def _bot_resource(token: str, session: AiohttpSession) -> Bot:
    bot = Bot(
        token=token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=session,
    )
    return bot


@asynccontextmanager
async def _event_bus_resource(
    rabbitmq_url: str | None,
    exchange: str,
    queue_name: str,
    prefetch_count: int,
) -> AsyncIterator[EventBus]:
    if rabbitmq_url:
        bus: EventBus = RabbitMQEventBus(
            rabbitmq_url,
            exchange=exchange,
            queue_name=queue_name,
            prefetch_count=prefetch_count,
        )
    else:
        bus = InMemoryEventBus()
    await bus.start()
    try:
        yield bus
    finally:
        await bus.stop()


@asynccontextmanager
async def _day_scheduler_resource(
    bus: EventBus, cron: str
) -> AsyncIterator[DayChangeScheduler]:
    # гарантируем наличие event loop
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        raise RuntimeError("init_resources() must be called inside an async context")
    scheduler = DayChangeScheduler(bus, cron=cron)
    scheduler.start()
    try:
        yield scheduler
    finally:
        scheduler.stop()


# ---------- DI container ----------


class AppContainer(containers.DeclarativeContainer):
    """Dependency Injector container for the app."""

    config = providers.Configuration()

    # Engine (sync resource)
    engine = providers.Resource(
        _engine_resource,
        database_url=config.database_url,
        echo=config.database_echo.as_bool(),
    )

    # Repositories
    watchlist_repo = providers.Singleton(SqliteWatchlistRepository, engine=engine)
    sub_state_repo = providers.Singleton(
        SqliteSubscriptionStateRepository, engine=engine
    )
    # Services
    watchlist_service = providers.Factory(WatchlistService, repo=watchlist_repo)

    # Twitch
    twitch_creds = providers.Singleton(
        TwitchAppCreds,
        client_id=config.twitch_client_id,
        client_secret=config.twitch_client_secret,
    )
    twitch_client = providers.Resource(_twitch_client_resource, creds=twitch_creds)

    # Telegram
    tg_session = providers.Resource(_aiohttp_session_resource)
    telegram_bot = providers.Resource(
        _bot_resource, token=config.telegram_bot_token, session=tg_session
    )
    notifier: providers.Singleton[NotifierProtocol] = providers.Singleton(
        TelegramNotifier, bot=telegram_bot, chat_id=config.telegram_chat_id
    )
    # Event bus (async resource to ensure graceful stop)
    event_bus = providers.Resource(
        _event_bus_resource,
        rabbitmq_url=config.rabbitmq_url.optional(),
        exchange=config.rabbitmq_exchange,
        queue_name=config.rabbitmq_queue,
        prefetch_count=config.rabbitmq_prefetch.as_int(),
    )
    # Day change scheduler (autostart on init_resources, stop on shutdown_resources)
    day_scheduler = providers.Resource(
        _day_scheduler_resource, bus=event_bus, cron=config.report_cron
    )

    # Application actors
    watcher = providers.Factory(
        Watcher,
        twitch=twitch_client,
        notifier=notifier,
        state_repo=sub_state_repo,
        event_bus=event_bus,
    )

    bot_app = providers.Factory(
        TelegramWatchlistBot,
        bot=telegram_bot,
        chat_id=config.telegram_chat_id,
        service=watchlist_service,
    )


# ---------- bootstrap helpers ----------


async def build_container(settings: Settings) -> AppContainer:
    """Create container, load config, init async resources."""
    container = AppContainer()
    container.config.from_pydantic(settings)  # pyright: ignore
    # Инициализируем все Resource провайдеры сразу
    aw = container.init_resources()
    if isinstance(aw, Awaitable):
        await aw
    return container


async def shutdown_container(container: AppContainer) -> None:
    """Graceful shutdown of resources."""
    aw = container.shutdown_resources()
    if isinstance(aw, Awaitable):
        await aw
