from typing import override


class InfraError(Exception):
    def message(self) -> str:
        return "Occur error in infrastructure layer."


class WatchListIsEmpty(InfraError):
    @override
    def message(self) -> str:
        return "Watchlist is empty"
