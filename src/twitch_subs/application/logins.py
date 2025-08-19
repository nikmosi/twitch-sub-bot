from abc import ABC, abstractmethod


class LoginsProvider(ABC):
    @abstractmethod
    def get(self) -> list[str]: ...
