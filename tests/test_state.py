from pathlib import Path

from twitch_subs.domain.models import BroadcasterType
from twitch_subs.infrastructure.state import StateRepository


def test_state_roundtrip(tmp_path: Path) -> None:
    repo = StateRepository(tmp_path / "state.json")
    state = {"foo": BroadcasterType.AFFILIATE}
    repo.save(state)
    loaded = repo.load()
    assert loaded == state
