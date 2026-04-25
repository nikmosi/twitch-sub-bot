from datetime import datetime, timezone

import pytest

from pydantic import ValidationError

from twitch_subs.domain.models import (
    BroadcasterType,
    SubState,
)


@pytest.mark.parametrize(
    "raw_broadcaster_type, expected_type",
    [
        (BroadcasterType.AFFILIATE, BroadcasterType.AFFILIATE),
        (BroadcasterType.NONE, BroadcasterType.NONE),
        ("partner", BroadcasterType.PARTNER),
    ],
)
def test_sub_state_normalizes_inputs(
    raw_broadcaster_type: BroadcasterType | str,
    expected_type: BroadcasterType,
) -> None:
    state = SubState(login="foo", broadcaster_type=raw_broadcaster_type)

    assert state.broadcaster_type is expected_type
    assert state.is_subscribed is expected_type.is_subscribable()


def test_sub_state_rejects_boolean_status() -> None:
    with pytest.raises(ValidationError):
        SubState(login="foo", broadcaster_type=True)


def test_sub_state_accepts_string_status() -> None:
    state = SubState(login="foo", broadcaster_type="partner")
    assert state.broadcaster_type is BroadcasterType.PARTNER


def test_sub_state_since_defaults_to_current_utc() -> None:
    state = SubState(login="foo")
    assert isinstance(state.since, datetime)
    assert state.since.tzinfo == timezone.utc
