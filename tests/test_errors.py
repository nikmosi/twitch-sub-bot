import asyncio
import logging

import pytest
from loguru import logger

from twitch_subs.errors import AppError
from twitch_subs.infrastructure.error import (
    AsyncTelegramNotifyError,
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
