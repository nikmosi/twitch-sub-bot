from twitch_subs.domain.models import BroadcasterType


def test_is_subscribable() -> None:
    assert BroadcasterType.AFFILIATE.is_subscribable()
    assert BroadcasterType.PARTNER.is_subscribable()
    assert not BroadcasterType.NONE.is_subscribable()
