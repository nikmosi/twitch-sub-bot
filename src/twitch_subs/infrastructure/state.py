from __future__ import annotations

from typing import Dict

from ..domain.models import BroadcasterType
from ..domain.ports import StateRepositoryProtocol


class StateRepository(StateRepositoryProtocol):
    """In-memory state repository used during runtime."""

    def __init__(self) -> None:
        self._state: Dict[str, BroadcasterType] = {}

    def load(self) -> Dict[str, BroadcasterType]:
        return dict(self._state)

    def save(self, state: Dict[str, BroadcasterType]) -> None:
        self._state = dict(state)
