"""Domain-level protocols for infrastructure concerns."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    """Provide the current time."""

    def now(self) -> datetime:  # pragma: no cover - protocol definition
        """Return the current timestamp in UTC."""


class IdProvider(Protocol):
    """Generate unique identifiers for domain entities and events."""

    def new_id(self) -> str:  # pragma: no cover - protocol definition
        """Return a new unique identifier."""

