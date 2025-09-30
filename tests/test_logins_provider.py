from collections import deque

from twitch_subs.application.logins import LoginsProvider
from twitch_subs.infrastructure.logins_provider import WatchListLoginProvider


class MemoryRepo:
    def __init__(self) -> None:
        self.calls = deque()

    def list(self) -> list[str]:
        self.calls.append("list")
        return ["b", "a"]


class DummyProvider(LoginsProvider):
    def get(self) -> list[str]:
        return ["x"]


def test_watchlist_login_provider_uses_repo() -> None:
    repo = MemoryRepo()
    provider = WatchListLoginProvider(repo)
    assert provider.get() == ["b", "a"]
    assert list(repo.calls) == ["list"]


def test_logins_provider_abc() -> None:
    provider = DummyProvider()
    assert provider.get() == ["x"]
