from __future__ import annotations

from dataclasses import dataclass, field

from twitch_subs.errors import AppError


@dataclass(frozen=True, slots=True)
class ApplicationError(AppError):
    """Base exception for application layer."""


@dataclass(frozen=True, slots=True)
class RepoCantFintLoginError(ApplicationError):
    login: str
    message: str = field(init=False)
    code: str = field(init=False, default="APP_REPO_LOOKUP_MISSING")
    context: dict[str, str] = field(init=False)

    def __post_init__(self) -> None:  # pragma: no cover - formatting helper
        object.__setattr__(
            self,
            "message",
            (
                "Repository returned None when it should return info about "
                f"{self.login}."
            ),
        )
        object.__setattr__(self, "context", {"login": self.login})


@dataclass(frozen=True, slots=True)
class WatcherRunError(ApplicationError):
    """Raised when Watcher.run_once fails unexpectedly."""

    logins: tuple[str, ...]
    error: Exception
    message: str = field(init=False, default="Watcher run_once failed")
    code: str = field(init=False, default="APP_WATCHER_RUN_FAILED")
    context: dict[str, object] = field(init=False)

    def __post_init__(self) -> None:  # pragma: no cover - formatting helper
        object.__setattr__(
            self, "context", {"logins": self.logins, "error": repr(self.error)}
        )
