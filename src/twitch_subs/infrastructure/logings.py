from __future__ import annotations

from twitch_subs.application.logins import LoginsProvider

from ..domain.ports import WatchlistRepository
from .error import WatchListIsEmpty


class WatchListLoginProvider(LoginsProvider):
    def __init__(self, repo: WatchlistRepository) -> None:
        self.repo = repo

    def get(self) -> list[str]:
        logins = self.repo.list()
        if not logins:
            raise WatchListIsEmpty()
        return logins
