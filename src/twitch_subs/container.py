from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass
from typing import Any

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from loguru import logger
from sqlalchemy import create_engine, text

from twitch_subs.application.ports import EventBus
from twitch_subs.application.reporting import DailyReportCollector, DayChangeScheduler
from twitch_subs.application.watchlist_service import WatchlistService
from twitch_subs.domain.events import (
    DayChanged,
    LoopChecked,
    LoopCheckFailed,
    OnceChecked,
    UserAdded,
    UserBecomeSubscribtable,
    UserRemoved,
)
from twitch_subs.infrastructure.event_bus.in_memory import InMemoryEventBus

from .application.watcher import Watcher
from .config import Settings
from .domain.models import LoginStatus, TwitchAppCreds
from .infrastructure.repository_sqlite import (
    SqliteSubscriptionStateRepository,
    SqliteWatchlistRepository,
    metadata,
)
from .infrastructure.telegram import TelegramNotifier, TelegramWatchlistBot
from .infrastructure.twitch import TwitchClient


@dataclass
class Container:
    """Build and provide application dependencies."""

    settings: Settings
    _engine: Any | None = None
    _watchlist_repo: SqliteWatchlistRepository | None = None
    _sub_state_repo: SqliteSubscriptionStateRepository | None = None
    _twitch: TwitchClient | None = None
    _notifier: TelegramNotifier | None = None
    _telegram_bot: Bot | None = None
    _tg_session: AiohttpSession | None = None
    _event_bus: EventBus | None = None
    _report_collector: DailyReportCollector | None = None
    _day_scheduler: DayChangeScheduler | None = None
    _day_scheduler_pending: bool = False

    @property
    def watchlist_service(self) -> WatchlistService:
        return WatchlistService(self.watchlist_repo)

    @property
    def engine(self):
        if self._engine is None:
            self._engine = create_engine(
                self.settings.database_url,
                echo=self.settings.database_echo,
                future=True,
            )
            with self._engine.begin() as conn:
                conn.execute(text("PRAGMA journal_mode=WAL"))
            metadata.create_all(self._engine)
        return self._engine

    @property
    def watchlist_repo(self) -> SqliteWatchlistRepository:
        if self._watchlist_repo is None:
            self._watchlist_repo = SqliteWatchlistRepository(self.engine)
        return self._watchlist_repo

    @property
    def sub_state_repo(self) -> SqliteSubscriptionStateRepository:
        if self._sub_state_repo is None:
            self._sub_state_repo = SqliteSubscriptionStateRepository(self.engine)
        return self._sub_state_repo

    @property
    def twitch_client(self) -> TwitchClient:
        if self._twitch is None:
            creds = TwitchAppCreds(
                client_id=self.settings.twitch_client_id,
                client_secret=self.settings.twitch_client_secret,
            )
            self._twitch = TwitchClient.from_creds(creds)
        return self._twitch

    @property
    def notifier(self) -> TelegramNotifier:
        if self._notifier is None:
            self._notifier = TelegramNotifier(
                self.telegram_bot,
                self.settings.telegram_chat_id,
            )
        return self._notifier

    def build_watcher(self) -> Watcher:
        watcher = Watcher(
            self.twitch_client, self.notifier, self.sub_state_repo, self.event_bus
        )
        self.ensure_day_scheduler()
        return watcher

    def build_bot(self) -> TelegramWatchlistBot:
        return TelegramWatchlistBot(
            self.telegram_bot,
            self.settings.telegram_chat_id,
            self.watchlist_service,
        )

    @property
    def telegram_bot(self) -> Bot:
        if self._tg_session is None:
            self._tg_session = AiohttpSession()
        if self._telegram_bot is None:
            bot_kwargs: dict[str, Any] = {
                "token": self.settings.telegram_bot_token,
                "default": DefaultBotProperties(parse_mode=ParseMode.HTML),
            }
            if "session" in inspect.signature(Bot).parameters:
                bot_kwargs["session"] = self._tg_session
            self._telegram_bot = Bot(**bot_kwargs)
        return self._telegram_bot

    @property
    def event_bus(self) -> EventBus:
        if self._event_bus is None:
            self._event_bus = InMemoryEventBus()

            notifier = self.notifier

            async def notify_about_add(event: UserAdded) -> None:
                await notifier.send_message(
                    f"➕ <code>{event.login}</code> добавлен в список наблюдения"
                )

            async def notify_about_remove(event: UserRemoved) -> None:
                await notifier.send_message(
                    f"➕ <code>{event.login}</code> добавлен в список наблюдения"
                )

            async def notify_about_subs_change(event: UserBecomeSubscribtable) -> None:
                await notifier.notify_about_change(
                    LoginStatus(event.login, event.current_state, None),
                    event.current_state,
                )

            async def log_once_check(event: OnceChecked) -> None:
                logger.debug(
                    f"checked {event.login} with status {event.current_state.value}."
                )

            async def log_loop_check(event: LoopChecked) -> None:
                logger.debug(f"checked {event.logins=}.")

            async def log_subs_change(event: UserBecomeSubscribtable) -> None:
                logger.info(f"{event.login} become {event.current_state.value}.")

            eb = self._event_bus
            eb.subscribe(UserAdded, notify_about_add)
            eb.subscribe(UserRemoved, notify_about_remove)
            eb.subscribe(UserBecomeSubscribtable, notify_about_subs_change)
            eb.subscribe(UserBecomeSubscribtable, log_subs_change)
            eb.subscribe(OnceChecked, log_once_check)
            eb.subscribe(LoopChecked, log_loop_check)

            collector = DailyReportCollector(notifier, self.sub_state_repo)
            self._report_collector = collector
            eb.subscribe(LoopChecked, collector.handle_loop_checked)
            eb.subscribe(LoopCheckFailed, collector.handle_loop_failed)
            eb.subscribe(DayChanged, collector.handle_day_changed)

        return self._event_bus

    def ensure_day_scheduler(self) -> None:
        if self._day_scheduler is None:
            self._day_scheduler = DayChangeScheduler(
                self.event_bus, cron=self.settings.report_cron
            )
            self._day_scheduler_pending = True

        if self._day_scheduler_pending:
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                return
            self._day_scheduler.start()
            self._day_scheduler_pending = False

    async def aclose(self) -> None:
        """Release resources created by the container."""

        try:
            if self._telegram_bot is not None and hasattr(self._telegram_bot, "close"):
                await self._telegram_bot.close()
            if self._tg_session is not None:
                await self._tg_session.close()
        finally:
            self._tg_session = None
            self._telegram_bot = None

        self._notifier = None

        if self._twitch is not None:
            self._twitch.close()
            self._twitch = None

        if self._engine is not None:
            self._engine.dispose()
            self._engine = None

        self._watchlist_repo = None
        self._sub_state_repo = None
        if self._day_scheduler is not None:
            self._day_scheduler.stop()
            self._day_scheduler = None
        self._day_scheduler_pending = False
        self._report_collector = None
