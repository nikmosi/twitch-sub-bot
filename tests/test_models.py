from datetime import datetime, timezone

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

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
    state = SubState("foo", BroadcasterType.NONE)
    end = datetime.now(timezone.utc)
    assert start <= state.updated_at <= end
    assert state.since is None


def test_unsubscribed_factory() -> None:
    fixed = datetime(2024, 1, 1, tzinfo=timezone.utc)
    state = SubState.unsubscribed("foo", updated_at=fixed)
    assert state.broadcaster_type is BroadcasterType.NONE
    assert state.is_subscribed is False
    assert state.since is None
    assert state.updated_at is fixed


@given(st.sampled_from(list(BroadcasterType)))
@settings(max_examples=50)
def test_substate_subscription_flag(btype: BroadcasterType) -> None:
    state = SubState("foo", btype)
    assert state.is_subscribed is btype.is_subscribable()
