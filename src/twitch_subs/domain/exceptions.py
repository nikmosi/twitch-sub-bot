from __future__ import annotations

from twitch_subs.errors import AppError


class DomainError(AppError):
    """Base exception for domain layer."""


class SigTerm(DomainError):
    """Raised when the application receives SIGTERM."""

    def __init__(self) -> None:
        super().__init__("Received SIGTERM", code="DOMAIN_SIGTERM")
