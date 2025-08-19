from twitch_subs.application.logins import LoginsProvider
from twitch_subs.infrastructure import watchlist
from twitch_subs.infrastructure.error import WatchListIsEmpty


class WatchListLoginProvider(LoginsProvider):
    def get(self) -> list[str]:
        path = watchlist.resolve_path()
        logins = watchlist.load(path)
        if not logins:
            raise WatchListIsEmpty()
        return logins
