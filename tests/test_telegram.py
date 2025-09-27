from __future__ import annotations

from typing import Any

import pytest

from twitch_subs.domain.models import BroadcasterType, LoginStatus, UserRecord
from twitch_subs.infrastructure.telegram import TelegramNotifier


class DummyBot:
    def __init__(self, token: str) -> None:
        self.token = token
        self.sent: list[dict[str, Any]] = []

    async def send_message(self, **kwargs: Any) -> None:
        self.sent.append(kwargs)


def test_send_message_uses_aiogram_bot() -> None:
    bot = DummyBot("tok")
    notifier = TelegramNotifier(bot, "chat")
    notifier.send_message(
        "hello", disable_web_page_preview=False, disable_notification=True
    )
    assert notifier.bot is bot
    assert bot.sent
    message = bot.sent[0]
    assert message["chat_id"] == "chat"
    assert message["text"] == "hello"
    assert message["disable_web_page_preview"] is False
    assert message["disable_notification"] is True


def test_send_message_swallow_errors() -> None:
    class FailBot(DummyBot):
        async def send_message(self, **kwargs: Any) -> None:  # noqa: ARG002
            raise RuntimeError("boom")

    from loguru import logger

    logger.disable("twitch_subs.infrastructure.telegram")
    try:
        notifier = TelegramNotifier(FailBot("tok"), "chat")
        notifier.send_message("hi")  # should not raise
    finally:
        logger.enable("twitch_subs.infrastructure.telegram")


def test_notify_about_change_formats(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_send(self: Any, text: str, **_: Any) -> None:
        calls.append(text)

    monkeypatch.setattr(TelegramNotifier, "send_message", fake_send)
    notifier = TelegramNotifier(DummyBot("t"), "c")
    status = LoginStatus(
        "foo",
        BroadcasterType.AFFILIATE,
        UserRecord("1", "foo", "Foo", BroadcasterType.AFFILIATE),
    )
    notifier.notify_about_change(status, BroadcasterType.PARTNER)
    assert calls and "<code>foo</code>" in calls[0]


def test_notify_report(monkeypatch: pytest.MonkeyPatch) -> None:
    messages: list[str] = []

    def fake_send(self: Any, text: str, **_: Any) -> None:
        messages.append(text)

    monkeypatch.setattr(TelegramNotifier, "send_message", fake_send)
    notifier = TelegramNotifier(DummyBot("t"), "c")
    state = {"foo": BroadcasterType.AFFILIATE}
    notifier.notify_report(["foo"], state, checks=1, errors=0)
    assert messages and "Checks: <b>1</b>" in messages[0]


def test_notify_start(monkeypatch: pytest.MonkeyPatch) -> None:
    messages: list[str] = []

    def fake_send(self: Any, text: str, **_: Any) -> None:
        messages.append(text)

    monkeypatch.setattr(TelegramNotifier, "send_message", fake_send)
    TelegramNotifier(DummyBot("t"), "c").notify_about_start()
    assert messages == ["🟢 <b>Twitch Subs Watcher</b> запущен. Мониторю."]
