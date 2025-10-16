import pytest
from datetime import datetime, timezone

from twitch_subs.domain.models import (
    BroadcasterType,
    LoginReportInfo,
    SubState,
)


def test_login_report_info_accepts_enum_and_str() -> None:
    enum_info = LoginReportInfo("foo", BroadcasterType.PARTNER)
    str_info = LoginReportInfo("foo", BroadcasterType.PARTNER.value)

    assert enum_info == str_info
    assert enum_info.tier == BroadcasterType.PARTNER.value
    assert enum_info.broadcaster is BroadcasterType.PARTNER


@pytest.mark.parametrize(
    "raw_status, tier, expected_type, expected_tier",
    [
        (True, BroadcasterType.AFFILIATE.value, BroadcasterType.AFFILIATE, BroadcasterType.AFFILIATE.value),
        (False, None, BroadcasterType.NONE, None),
        (True, "invalid", BroadcasterType.AFFILIATE, BroadcasterType.AFFILIATE.value),
    ],
)
def test_sub_state_normalizes_inputs(
    raw_status: bool, tier: str | None, expected_type: BroadcasterType, expected_tier: str | None
) -> None:
    state = SubState(
        "foo",
        raw_status,
        tier=tier,
        updated_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )

    assert state.status is expected_type
    assert state.tier == expected_tier
    assert state.is_subscribed is expected_type.is_subscribable()
