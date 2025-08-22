from twitch_subs.domain.models import BroadcasterType
from twitch_subs.infrastructure.state import StateRepository


def test_state_roundtrip() -> None:
    repo = StateRepository()
    state = {"foo": BroadcasterType.AFFILIATE}
    repo.save(state)
    loaded = repo.load()
    assert loaded == state
