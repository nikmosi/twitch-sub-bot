import pytest

from twitch_subs.domain.models import BroadcasterType, State


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
