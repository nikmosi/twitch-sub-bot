from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class ApplicationBaseError(Exception):
    @property
    def message(self) -> str:
        return "Occur error in application layer."


@dataclass(frozen=True, slots=True, kw_only=True)
class RepoCantFintLoginError(Exception):
    login: str

    @property
    def message(self) -> str:
        return f"Repository return None, when shouldn't return info about {self.login}."
