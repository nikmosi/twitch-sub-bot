from __future__ import annotations

from dataclasses import dataclass

from twitch_subs.application.watchlist_service import WatchlistService

from .application.watcher import Watcher
from .config import Settings
from .domain.models import TwitchAppCreds
from .infrastructure.repository_sqlite import SqliteWatchlistRepository
from .infrastructure.state import MemoryStateRepository
from .infrastructure.telegram import TelegramNotifier, TelegramWatchlistBot
from .infrastructure.twitch import TwitchClient


@dataclass
class Container:
    """Build and provide application dependencies."""

    settings: Settings
    _watchlist_repo: SqliteWatchlistRepository | None = None
    _twitch: TwitchClient | None = None
    _notifier: TelegramNotifier | None = None
    _state_repo: MemoryStateRepository | None = None

    @property
    def watchlist_service(self) -> WatchlistService:
        return WatchlistService(self.watchlist_repo)

    @property
    def watchlist_repo(self) -> SqliteWatchlistRepository:
        if self._watchlist_repo is None:
            self._watchlist_repo = SqliteWatchlistRepository(
                self.settings.database_url, self.settings.database_echo
            )
        return self._watchlist_repo

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
                self.settings.telegram_bot_token,
                self.settings.telegram_chat_id,
            )
        return self._notifier

    @property
    def state_repo(self) -> MemoryStateRepository:
        if self._state_repo is None:
            self._state_repo = MemoryStateRepository()
        return self._state_repo

    def build_watcher(self) -> Watcher:
        return Watcher(self.twitch_client, self.notifier, self.state_repo)

    def build_bot(self) -> TelegramWatchlistBot:
        return TelegramWatchlistBot(
            self.settings.telegram_bot_token,
            self.settings.telegram_chat_id,
            self.watchlist_service,
        )
