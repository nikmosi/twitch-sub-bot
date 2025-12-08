from __future__ import annotations

from twitch_subs.errors import AppError


class ApplicationError(AppError):
    """Base exception for application layer."""


class RepoCantFintLoginError(ApplicationError):
    def __init__(self, login: str) -> None:
        super().__init__(
            message=(
                f"Repository returned None when it should return info about {login}."
            ),
            context={"login": login},
            code="APP_REPO_LOOKUP_MISSING",
        )
        self.login = login


class WatcherRunError(ApplicationError):
    """Raised when Watcher.run_once fails unexpectedly."""

    def __init__(self, logins: tuple[str, ...], error: Exception) -> None:
        super().__init__(
            message="Watcher run_once failed",
            context={"logins": logins, "error": repr(error)},
            code="APP_WATCHER_RUN_FAILED",
        )
        self.logins = logins
