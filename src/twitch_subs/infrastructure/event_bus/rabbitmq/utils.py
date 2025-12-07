"""RabbitMQ-backed event bus implementation."""

from __future__ import annotations

import re
from typing import Any, TypeVar

from loguru import logger

from twitch_subs.domain.events import DomainEvent

LOGGER = logger

T = TypeVar("T", bound=DomainEvent)
_EVENT_VERSION = 1

_CAMEL_SPLIT = re.compile(r"[A-Z]+(?=[A-Z][a-z]|$)|[A-Z]?[a-z]+|\d+")


def routing_key_from_type(tp: type[DomainEvent]) -> str:
    # Опциональные переопределения на классе события
    rk = getattr(tp, "ROUTING_KEY", None)
    if isinstance(rk, str) and rk:
        return rk
    prefix = getattr(tp, "ROUTING_PREFIX", "domain")
    name = tp.name()
    parts = _CAMEL_SPLIT.findall(name)
    return f"{prefix}." + ".".join(p.lower() for p in parts)


def serialize_event(event: DomainEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "occurred_at": event.occurred_at.isoformat(),
        "name": event.name(),
        "version": _EVENT_VERSION,
        "payload": event.model_dump(mode="json", exclude={"id", "occurred_at"}),
    }
