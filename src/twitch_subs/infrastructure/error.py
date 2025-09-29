from dataclasses import dataclass
from typing import override


class InfraError(Exception):
    def message(self) -> str:
        return "Occur error in infrastructure layer."


class WatchListIsEmpty(InfraError):
    @override
    def message(self) -> str:
        return "Watchlist is empty"


@dataclass
class AsyncTelegramNotifyError(InfraError):
    exception: RuntimeError

    @override
    def message(self) -> str:
        return f"Occur Runtime error with msg: {self.exception}"


@dataclass
class CantGetCurrentEventLoop(InfraError):
    @override
    def message(self) -> str:
        return "Can't get event loop."
