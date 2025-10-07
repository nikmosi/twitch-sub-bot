from __future__ import annotations

from .ports import WatchlistRepository


class WatchlistService:
    """High level API for watchlist operations."""

    def __init__(self, repo: WatchlistRepository) -> None:
        self.repo = repo

    def add(self, login: str) -> bool:
        """Add *login* to the watchlist.

        Returns ``True`` if added, ``False`` if already present.
        """
        if self.repo.exists(login):
            return False
        self.repo.add(login)
        return True

    def remove(self, login: str) -> bool:
        """Remove *login* from the watchlist.

        Returns ``True`` if *login* was present and removed.
        """
        return self.repo.remove(login)

    def list(self) -> list[str]:
        """Return all logins sorted alphabetically."""
        return self.repo.list()
