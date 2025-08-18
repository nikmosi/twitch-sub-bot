from pathlib import Path

from twitch_subs.domain.models import BroadcasterType
from twitch_subs.infrastructure.state import StateRepository


def test_state_roundtrip(tmp_path: Path) -> None:
    repo = StateRepository(tmp_path / "state.json")
    state = {"foo": BroadcasterType.AFFILIATE}
    repo.save(state)
    loaded = repo.load()
    assert loaded == state


def test_load_returns_empty_when_missing(tmp_path: Path) -> None:
    repo = StateRepository(tmp_path / "state.json")
    assert repo.load() == {}


def test_load_returns_empty_on_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text("not-json")
    repo = StateRepository(path)
    assert repo.load() == {}
