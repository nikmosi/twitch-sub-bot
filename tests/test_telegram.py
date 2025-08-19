from typing import Any

import httpx
from pytest import MonkeyPatch

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


def test_send_message_builds_request(monkeypatch: MonkeyPatch) -> None:
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


def test_send_message_swallow_errors(monkeypatch: MonkeyPatch) -> None:
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
    notifier = TelegramNotifier("tok", "chat")
    notifier.send_message("hi")  # should not raise
