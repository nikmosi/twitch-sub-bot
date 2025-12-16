from __future__ import annotations

from twitch_subs.application.logins import LoginsProvider
from twitch_subs.application.ports import WatchlistRepository


class WatchListLoginProvider(LoginsProvider):
    def __init__(self, repo: WatchlistRepository) -> None:
        self.repo = repo

    def get(self) -> list[str]:
        logins = self.repo.get_list()
        return logins
