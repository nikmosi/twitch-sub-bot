from twitch_subs.domain.models import BroadcasterType, State
from twitch_subs.infrastructure.state import MemoryStateRepository


def test_state_roundtrip() -> None:
    repo = MemoryStateRepository()
    state = State({"foo": BroadcasterType.AFFILIATE})
    repo.save(state)
    loaded = repo.load()
    assert loaded == state
