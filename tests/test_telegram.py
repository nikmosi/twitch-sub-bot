import httpx

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
    def __init__(self, *args, **kwargs) -> None:
        self.posts: list[tuple[str, dict]] = []

    def __enter__(self) -> "DummyClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: D401
        pass

    def post(self, url: str, json: dict) -> DummyResponse:
        self.posts.append((url, json))
        return DummyResponse()


def test_send_message_builds_request(monkeypatch) -> None:
    client = DummyClient()
    monkeypatch.setattr(httpx, "Client", lambda *a, **k: client)
    notifier = TelegramNotifier("tok", "chat")
    notifier.send_message("hello", disable_web_page_preview=False)
    assert client.posts
    url, payload = client.posts[0]
    assert url == f"{TELEGRAM_API_BASE}/bot{'tok'}/sendMessage"
    assert payload["chat_id"] == "chat"
    assert payload["text"] == "hello"
    assert payload["disable_web_page_preview"] is False


def test_send_message_swallow_errors(monkeypatch) -> None:
    class FailClient:
        def __init__(self, *a, **k) -> None:
            pass

        def __enter__(self) -> "FailClient":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:  # noqa: D401
            pass

        def post(self, url: str, json: dict) -> None:
            raise httpx.HTTPError("boom")

    monkeypatch.setattr(httpx, "Client", lambda *a, **k: FailClient())
    notifier = TelegramNotifier("tok", "chat")
    notifier.send_message("hi")  # should not raise
