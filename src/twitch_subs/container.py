from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from aiogram import Bot
from aiogram.client.bot import DefaultBotProperties
from aiogram.enums import ParseMode
from sqlalchemy import create_engine, text

from twitch_subs.application.watchlist_service import WatchlistService

from .application.watcher import Watcher
from .config import Settings
from .domain.models import TwitchAppCreds
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
        return Watcher(self.twitch_client, self.notifier, self.sub_state_repo)

    def build_bot(self) -> TelegramWatchlistBot:
        return TelegramWatchlistBot(
            self.telegram_bot,
            self.settings.telegram_chat_id,
            self.watchlist_service,
        )

    @property
    def telegram_bot(self) -> Bot:
        if self._telegram_bot is None:
            self._telegram_bot = Bot(
                token=self.settings.telegram_bot_token,
                default=DefaultBotProperties(parse_mode=ParseMode.HTML),
            )
        return self._telegram_bot
