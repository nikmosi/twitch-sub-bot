from typing import override


class AppException(Exception):
    def message(self) -> str:
        return "Occur error in app"


class SigTerm(AppException):
    @override
    def message(self) -> str:
        return "Got SigTerm"
