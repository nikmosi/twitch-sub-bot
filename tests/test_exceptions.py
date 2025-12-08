from twitch_subs.domain.exceptions import DomainError, SigTerm


def test_domain_error_inheritance() -> None:
    err = DomainError("boom", code="CODE")
    assert err.message == "boom"
    assert err.code == "CODE"


def test_sigterm_message_and_inheritance() -> None:
    e = SigTerm()
    assert e.message == "Received SIGTERM"
    assert isinstance(e, DomainError)
