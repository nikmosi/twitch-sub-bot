from __future__ import annotations

from ..domain.models import BroadcasterType, State
from ..domain.ports import StateRepositoryProtocol


class MemoryStateRepository(StateRepositoryProtocol):
    """In-memory state repository used during runtime."""

    def __init__(self) -> None:
        self._state = State()

    def load(self) -> State:
        return self._state.copy()

    def save(self, state: State) -> None:
        self._state = state.copy()
