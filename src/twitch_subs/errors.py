from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class AppError(Exception):
    """Base error for all layers.

    Attributes:
        message: Human-readable message describing the error.
        code: Optional machine-readable code for monitoring/alerts.
        context: Optional structured context for diagnostics.
    """

    message: str
    code: str | None = None
    context: Mapping[str, Any] | None = None

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.message
