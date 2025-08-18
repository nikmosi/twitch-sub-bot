from typing import override


class AppException(Exception):
    """Base application exception."""

    def message(self) -> str:
        return "Application error"


class SigTerm(AppException):
    """Raised when the application receives SIGTERM."""

    @override
    def message(self) -> str:
        return "Received SIGTERM"
