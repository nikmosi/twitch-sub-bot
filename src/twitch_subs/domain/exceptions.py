from __future__ import annotations

from dataclasses import dataclass, field

from twitch_subs.errors import AppError


@dataclass(frozen=True, slots=True)
class DomainError(AppError):
    """Base exception for domain layer."""


@dataclass(frozen=True, slots=True)
class SigTerm(DomainError):
    """Raised when the application receives SIGTERM."""

    message: str = field(init=False, default="Received SIGTERM")
    code: str = field(init=False, default="DOMAIN_SIGTERM")
