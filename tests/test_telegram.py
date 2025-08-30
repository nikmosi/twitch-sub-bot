from typing import Any

import httpx
import pytest

from twitch_subs.domain.models import BroadcasterType, LoginStatus, UserRecord
from twitch_subs.infrastructure.telegram import (
    TELEGRAM_API_BASE,
    TelegramNotifier,
)


class DummyResponse:
    def __init__(self) -> None:
        self.status_checked = False

    def raise_for_status(self) -> None:
        self.status_checked = True


class DummyClient:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        _ = args
        _ = kwargs
        self.posts: list[tuple[str, dict[Any, Any]]] = []

    def __enter__(self) -> "DummyClient":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:  # noqa: D401
        _ = exc_type
        _ = exc
        _ = tb

        pass

    def post(self, url: str, json: dict[Any, Any]) -> DummyResponse:
        self.posts.append((url, json))
        return DummyResponse()


def test_send_message_builds_request(monkeypatch: pytest.MonkeyPatch) -> None:
    client = DummyClient()
    monkeypatch.setattr(httpx, "Client", lambda **_: client)  # pyright: ignore
    notifier = TelegramNotifier("tok", "chat")
    notifier.send_message(
        "hello", disable_web_page_preview=False, disable_notification=True
    )
    assert client.posts
    url, payload = client.posts[0]
    assert url == f"{TELEGRAM_API_BASE}/bot{'tok'}/sendMessage"
    assert payload["chat_id"] == "chat"
    assert payload["text"] == "hello"
    assert payload["disable_web_page_preview"] is False
    assert payload["disable_notification"] is True


def test_send_message_swallow_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    class FailClient:
        def __init__(self, **_) -> None:
            pass

        def __enter__(self) -> "FailClient":
            return self

        def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:  # noqa: D401
            _ = exc_type
            _ = exc
            _ = tb
            pass

        def post(self, url: str, json: dict[Any, Any]) -> None:
            _ = url
            _ = json
            raise httpx.HTTPError("boom")

    monkeypatch.setattr(httpx, "Client", lambda **_: FailClient())  # pyright: ignore

    from loguru import logger

    logger.disable("twitch_subs.infrastructure.telegram")
    try:
        notifier = TelegramNotifier("tok", "chat")
        notifier.send_message("hi")  # should not raise
    finally:
        logger.enable("twitch_subs.infrastructure.telegram")


def test_notify_about_change_formats(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_send(self: Any, text: str, **_: Any) -> None:
        calls.append(text)

    monkeypatch.setattr(TelegramNotifier, "send_message", fake_send)
    notifier = TelegramNotifier("t", "c")
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
    notifier = TelegramNotifier("t", "c")
    state = {"foo": BroadcasterType.AFFILIATE}
    notifier.notify_report(["foo"], state, checks=1, errors=0)
    assert messages and "Checks: <b>1</b>" in messages[0]


def test_notify_start(monkeypatch: pytest.MonkeyPatch) -> None:
    messages: list[str] = []

    def fake_send(self: Any, text: str, **_: Any) -> None:
        messages.append(text)

    monkeypatch.setattr(TelegramNotifier, "send_message", fake_send)
    TelegramNotifier("t", "c").notify_about_start()
    assert messages == ["🟢 <b>Twitch Subs Watcher</b> запущен. Мониторю."]
