from twitch_subs.infrastructure.error import InfraError, WatchListIsEmpty


def test_infra_error_message() -> None:
    assert InfraError().message() == "Occur error in infrastructure layer."


def test_watchlist_is_empty_message() -> None:
    assert WatchListIsEmpty().message() == "Watchlist is empty"
