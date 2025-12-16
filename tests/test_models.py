import pytest

from pydantic import ValidationError

from twitch_subs.domain.models import (
    BroadcasterType,
    LoginReportInfo,
    SubState,
)


def test_login_report_info_accepts_enum_and_str() -> None:
    enum_info = LoginReportInfo(login="foo", broadcaster=BroadcasterType.PARTNER)
    str_info = LoginReportInfo(login="foo", broadcaster=BroadcasterType.PARTNER.value)

    assert enum_info == str_info
    assert enum_info.broadcaster == BroadcasterType.PARTNER
    assert enum_info.broadcaster is BroadcasterType.PARTNER


def test_login_report_info_none_defaults_to_none() -> None:
    with pytest.raises(ValidationError):
        LoginReportInfo(login="bar", broadcaster=None)


@pytest.mark.parametrize(
    "raw_status, tier, expected_type, expected_tier",
    [
        (
            BroadcasterType.AFFILIATE,
            BroadcasterType.AFFILIATE.value,
            BroadcasterType.AFFILIATE,
            BroadcasterType.AFFILIATE.value,
        ),
        (BroadcasterType.NONE, None, BroadcasterType.NONE, None),
        ("partner", None, BroadcasterType.PARTNER, None),
    ],
)
def test_sub_state_normalizes_inputs(
    raw_status: BroadcasterType | str,
    tier: str | None,
    expected_type: BroadcasterType,
    expected_tier: str | None,
) -> None:
    state = SubState(login="foo", status=raw_status, tier=tier)

    assert state.status is expected_type
    assert state.tier == expected_tier
    assert state.is_subscribed is expected_type.is_subscribable()


def test_sub_state_rejects_boolean_status() -> None:
    with pytest.raises(ValidationError):
        SubState(login="foo", status=True, tier="affiliate")


def test_sub_state_accepts_string_status() -> None:
    state = SubState(login="foo", status="partner")
    assert state.status is BroadcasterType.PARTNER
    assert state.tier is None
