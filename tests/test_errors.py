import asyncio
import logging

import pytest
from loguru import logger

from twitch_subs.application.error import RepoCantFintLoginError, WatcherRunError
from twitch_subs.errors import AppError
from twitch_subs.infrastructure.error import (
    AsyncTelegramNotifyError,
    CantExtractNicknama,
    InfraError,
    NotificationDeliveryError,
    WatchListIsEmpty,
)
from twitch_subs.infrastructure.notifier.console import ConsoleNotifier
from twitch_subs.infrastructure.notifier.telegram import TelegramNotifier


def test_app_error_str() -> None:
    err = AppError("msg", code="X", context={"foo": "bar"})
    assert str(err) == "msg"
    assert err.code == "X" and err.context == {"foo": "bar"}


def test_infra_error_subclasses() -> None:
    assert WatchListIsEmpty().message == "Watchlist is empty"
    assert isinstance(WatchListIsEmpty(), InfraError)


def test_application_error_messages_and_context() -> None:
    repo_error = RepoCantFintLoginError(login="alice")
    assert repo_error.message.endswith("alice.")
    assert repo_error.context == {"login": "alice"}

    watcher_error = WatcherRunError(logins=("bob",), error=RuntimeError("boom"))
    assert watcher_error.message == "Watcher run_once failed"
    assert watcher_error.context == {"logins": ("bob",), "error": "RuntimeError('boom')"}


def test_cant_extract_nicknama_message_and_context() -> None:
    error = CantExtractNicknama(nickname="bad url")
    assert error.message == "Can't extract nickname from bad url"
    assert error.context == {"nickname": "bad url"}


@pytest.mark.asyncio
async def test_console_notifier_logs_and_raises(caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch) -> None:
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
async def test_telegram_notifier_logs_and_raises(caplog: pytest.LogCaptureFixture) -> None:
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
