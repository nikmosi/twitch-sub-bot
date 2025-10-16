"""Infrastructure implementations for system-provided services."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from twitch_subs.domain.protocols import Clock, IdProvider


class SystemClock(Clock):
    """Return the current UTC timestamp using :func:`datetime.now`."""

    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class Uuid4Provider(IdProvider):
    """Generate UUID4 identifiers."""

    def new_id(self) -> str:
        return str(uuid.uuid4())

