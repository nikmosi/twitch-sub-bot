import logging

import pytest
from loguru import logger

from twitch_subs.application.error import RepositoryLoginNotFoundError, WatcherRunError
from twitch_subs.errors import AppError
from twitch_subs.infrastructure.error import (
    AsyncTelegramNotifyError,
    NicknameExtractionError,
    InfraError,
    NotificationDeliveryError,
    WatchlistIsEmpty,
)
from twitch_subs.infrastructure.notifier.console import ConsoleNotifier
from twitch_subs.infrastructure.notifier.telegram import TelegramNotifier


def test_app_error_str() -> None:
    err = AppError("msg", code="X", context={"foo": "bar"})
    assert str(err) == "msg"
    assert err.code == "X" and err.context == {"foo": "bar"}


def test_infra_error_subclasses() -> None:
    assert WatchlistIsEmpty().message.startswith("The watchlist is empty")
    assert isinstance(WatchlistIsEmpty(), InfraError)


def test_application_error_messages_and_context() -> None:
    repo_error = RepositoryLoginNotFoundError(login="alice")
    assert "alice" in repo_error.message
    assert repo_error.context == {"login": "alice"}

    watcher_error = WatcherRunError(logins=("bob",), error=RuntimeError("boom"))
    assert watcher_error.message == "Watcher run_once failed"
    assert watcher_error.context == {
        "logins": ("bob",),
        "error": "RuntimeError('boom')",
    }


def test_nickname_extraction_error_message_and_context() -> None:
    error = NicknameExtractionError(nickname="bad url")
    assert "bad url" in error.message
    assert error.context == {"nickname": "bad url"}


@pytest.mark.asyncio
async def test_console_notifier_logs_and_raises(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    notifier = ConsoleNotifier()

    def boom(_: str) -> str:
        raise ValueError("console boom")

    monkeypatch.setattr(
        "twitch_subs.infrastructure.notifier.console._html_to_plain",
        boom,
    )
    caplog.set_level(logging.ERROR)
    sink_id = logger.add(caplog.handler, level="ERROR", format="{message}")
    with pytest.raises(NotificationDeliveryError):
        await notifier.send_message("text")
    logger.remove(sink_id)
    assert "console boom" in caplog.text


@pytest.mark.asyncio
async def test_telegram_notifier_logs_and_raises(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class FailingBot:
        async def send_message(self, *args, **kwargs):  # type: ignore[override]
            raise RuntimeError("tg boom")

    notifier = TelegramNotifier(FailingBot(), "chat")
    caplog.set_level(logging.ERROR)
    sink_id = logger.add(caplog.handler, level="ERROR", format="{message}")
    with pytest.raises(AsyncTelegramNotifyError):
        await notifier.send_message("text")
    logger.remove(sink_id)
    assert "tg boom" in caplog.text
