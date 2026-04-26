from datetime import datetime, timezone

import pytest

from pydantic import ValidationError

from twitch_subs.domain.models import (
    BroadcasterType,
    SubState,
    TwitchUsername,
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


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("foo", "foo"),
        ("User_123", "User_123"),
        ("https://twitch.tv/foo", "foo"),
        ("https://www.twitch.tv/User_123/", "User_123"),
        ("https://m.twitch.tv/bar_1", "bar_1"),
    ],
)
def test_twitch_username_parses_username_and_twitch_urls(
    raw: str, expected: str
) -> None:
    username = TwitchUsername.parse_from_token(raw)

    assert username.value == expected
    assert str(username) == expected


@pytest.mark.parametrize(
    "raw",
    ["ab", "a" * 26, "bad-name", "юзер", "https://twitch.tv/юзер", ""],
)
def test_twitch_username_rejects_invalid_values(raw: str) -> None:
    with pytest.raises(ValueError):
        TwitchUsername.parse_from_token(raw)


def test_twitch_username_parse_from_text_splits_any_whitespace() -> None:
    usernames = TwitchUsername.parse_from_text("foo   bar\tbaz")

    assert [username.value for username in usernames] == ["foo", "bar", "baz"]
