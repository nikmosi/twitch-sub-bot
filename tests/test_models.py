from datetime import datetime, timezone

import pytest

from twitch_subs.domain.models import BroadcasterType, SubState


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


def test_substate_updated_at_defaults_to_utc() -> None:
    start = datetime.now(timezone.utc)
    state = SubState("foo", False)
    end = datetime.now(timezone.utc)
    assert start <= state.updated_at <= end
    assert state.since is None
