from twitch_subs.domain.exceptions import AppException, SigTerm


def test_app_exception_message() -> None:
    e = AppException()
    assert e.message() == "Application error"


def test_sigterm_message_and_inheritance() -> None:
    e = SigTerm()
    assert e.message() == "Received SIGTERM"
    assert isinstance(e, AppException)
