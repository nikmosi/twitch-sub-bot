from datetime import datetime, timezone

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from twitch_subs.domain.models import BroadcasterType, State, SubState


@pytest.mark.parametrize(
    "btype,expected",
    [
        (BroadcasterType.NONE, False),
        (BroadcasterType.AFFILIATE, True),
        (BroadcasterType.PARTNER, True),
    ],
)
def test_is_subscribable(btype: BroadcasterType, expected: bool) -> None:
    assert btype.is_subscribable() is expected


def test_state_mapping_operations() -> None:
    st = State()
    st["foo"] = BroadcasterType.NONE
    assert list(iter(st)) == ["foo"]
    assert len(st) == 1
    del st["foo"]
    assert len(st) == 0


def test_substate_updated_at_defaults_to_utc() -> None:
    start = datetime.now(timezone.utc)
    state = SubState("foo", False)
    end = datetime.now(timezone.utc)
    assert start <= state.updated_at <= end
    assert state.since is None


@given(
    st.dictionaries(keys=st.text(min_size=1, max_size=5), values=st.sampled_from(list(BroadcasterType))),
)
@settings(max_examples=50)
def test_state_copy_property(data: dict[str, BroadcasterType]) -> None:
    state = State(data.copy())
    clone = state.copy()
    assert dict(clone) == dict(state)
    clone["new"] = BroadcasterType.NONE
    assert "new" not in state
