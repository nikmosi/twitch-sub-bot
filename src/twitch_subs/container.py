# container_di.py
from __future__ import annotations

from contextlib import asynccontextmanager, contextmanager
from typing import AsyncContextManager, AsyncIterator, Awaitable, Iterator

import aio_pika
from aio_pika.abc import AbstractRobustConnection
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiolimiter import AsyncLimiter
from dependency_injector import containers, providers
from sqlalchemy import Engine, create_engine, text

from twitch_subs.application.ports import (
    EventBus,
    NotifierProtocol,
    SubscriptionStateRepo,
    TwitchClientProtocol,
)
from twitch_subs.application.watchlist_service import WatchlistService
from twitch_subs.domain.models import TwitchAppCreds
from twitch_subs.infrastructure.event_bus import RabbitMQEventBus
from twitch_subs.infrastructure.event_bus.rabbitmq.consumer import Consumer
from twitch_subs.infrastructure.event_bus.rabbitmq.producer import Producer
from twitch_subs.infrastructure.notifier.telegram import TelegramNotifier
from twitch_subs.infrastructure.repository_sqlite import (
    SqliteSubscriptionStateRepository,
    SqliteWatchlistRepository,
    metadata,
)
from twitch_subs.infrastructure.telegram import TelegramWatchlistBot
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


def _build_bot(
    *, token: str, default: DefaultBotProperties, session: AiohttpSession
) -> Bot:
    return Bot(token=token, default=default, session=session)


@asynccontextmanager
async def _twitch_client_resource(
    creds: TwitchAppCreds, async_limiter: AsyncLimiter | None = None
) -> AsyncIterator[TwitchClient]:
    client = TwitchClient(
        creds.client_id, creds.client_secret, async_limiter=async_limiter
    )
    try:
        yield client
    finally:
        await client.aclose()


@asynccontextmanager
async def _rabbit_event_bus_resource(
    producer: Producer,
    consumer: Consumer,
) -> AsyncIterator[EventBus]:
    bus: EventBus = RabbitMQEventBus(producer=producer, consumer=consumer)
    async with bus:
        yield bus


@asynccontextmanager
async def _rabbitmq_resource(url: str) -> AsyncIterator[AbstractRobustConnection]:
    connection = await aio_pika.connect_robust(url=url)
    try:
        yield connection
    finally:
        await connection.close()


@asynccontextmanager
async def _create_watcher(
    twitch: TwitchClientProtocol,
    notifier: NotifierProtocol,
    state_repo: SubscriptionStateRepo,
    event_bus_fac: AsyncContextManager[EventBus],
) -> AsyncIterator[Watcher]:
    try:
        async with event_bus_fac as event_bus:
            yield Watcher(
                twitch=twitch,
                notifier=notifier,
                state_repo=state_repo,
                event_bus=event_bus,
            )
    except GeneratorExit:
        return


@asynccontextmanager
async def _create_telegram_watchlist_bot(
    bot: Bot,
    chat_id: str,
    service: WatchlistService,
    event_bus_fac: AsyncContextManager[EventBus],
) -> AsyncIterator[TelegramWatchlistBot]:
    try:
        async with event_bus_fac as event_bus:
            yield TelegramWatchlistBot(
                bot=bot,
                chat_id=chat_id,
                service=service,
                event_bus=event_bus,
            )
    except GeneratorExit:
        return


# ---------- DI container ----------
class AppContainer(containers.DeclarativeContainer):
    """Dependency Injector container for the app."""

    settings = providers.Singleton(Settings)
    container_config = providers.Configuration()

    # Engine (sync resource)
    engine = providers.Resource(
        _engine_resource,
        database_url=container_config.database_url,
        echo=container_config.database_echo.as_bool(),
    )

    rabbit_conn = providers.Resource(_rabbitmq_resource, container_config.rabbitmq_url)

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
        client_id=container_config.twitch_client_id,
        client_secret=container_config.twitch_client_secret,
    )
    async_limiter = providers.Factory(
        AsyncLimiter,
        container_config.limiter_max_rate,
        container_config.limiter_time_period,
    )
    twitch_client = providers.Resource(
        _twitch_client_resource, creds=twitch_creds, async_limiter=async_limiter
    )

    # Telegram
    tg_session = providers.Resource(_aiohttp_session_resource)
    telegram_bot = providers.Resource(
        _build_bot,
        token=container_config.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=tg_session,
    )
    notifier: providers.Singleton[NotifierProtocol] = providers.Singleton(
        TelegramNotifier, bot=telegram_bot, chat_id=container_config.telegram_chat_id
    )
    consumer = providers.Singleton(
        Consumer,
        connection=rabbit_conn,
        exchange=container_config.rabbitmq_exchange,
        queue_name=container_config.rabbitmq_queue,
        prefetch_count=container_config.rabbitmq_prefetch.as_int(),
    )
    producer = providers.Singleton(Producer, connection=rabbit_conn)
    event_bus_factory = providers.Factory(
        _rabbit_event_bus_resource,
        consumer=consumer,
        producer=producer,
    )

    # Application actors
    watcher = providers.Factory(
        _create_watcher,
        twitch=twitch_client,
        notifier=notifier,
        state_repo=sub_state_repo,
        event_bus_fac=event_bus_factory,
    )

    bot_app = providers.Factory(
        _create_telegram_watchlist_bot,
        bot=telegram_bot,
        chat_id=container_config.telegram_chat_id,
        service=watchlist_service,
        event_bus_fac=event_bus_factory,
    )


# ---------- bootstrap helpers ----------


async def build_container(settings: Settings) -> AppContainer:
    """Create container, load config, init async resources."""
    container = AppContainer()
    container.container_config.from_pydantic(settings)  # pyright: ignore
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
