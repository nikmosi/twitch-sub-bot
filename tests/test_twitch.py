import httpx

from twitch_subs.domain.models import BroadcasterType, TwitchAppCreds
from twitch_subs.infrastructure.twitch import (
    TWITCH_TOKEN_URL,
    TWITCH_USERS_URL,
    TwitchClient,
)


class DummyResponse:
    def __init__(self, data: dict) -> None:
        self._data = data
        self.status_checked = False

    def json(self) -> dict:
        return self._data

    def raise_for_status(self) -> None:
        self.status_checked = True


class DummyClient:
    def __init__(self, responses: list[DummyResponse]) -> None:
        self.responses = responses
        self.requests: list[tuple] = []

    def __enter__(self) -> "DummyClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: D401
        pass

    def post(self, url: str, data: dict | None = None) -> DummyResponse:
        self.requests.append(("POST", url, data))
        return self.responses.pop(0)

    def get(self, url: str, headers: dict | None = None, params: dict | None = None) -> DummyResponse:
        self.requests.append(("GET", url, headers, params))
        return self.responses.pop(0)


def test_from_creds_requests_token(monkeypatch) -> None:
    responses = [DummyResponse({"access_token": "abc"})]
    client = DummyClient(responses)
    monkeypatch.setattr(httpx, "Client", lambda *a, **k: client)
    creds = TwitchAppCreds(client_id="id", client_secret="secret")
    twitch = TwitchClient.from_creds(creds)
    assert isinstance(twitch, TwitchClient)
    method, url, data = client.requests[0]
    assert method == "POST" and url == TWITCH_TOKEN_URL
    assert data["client_id"] == "id"


def test_get_user_by_login_returns_user(monkeypatch) -> None:
    responses = [
        DummyResponse(
            {
                "data": [
                    {
                        "id": "1",
                        "login": "foo",
                        "display_name": "Foo",
                        "broadcaster_type": "partner",
                    }
                ]
            }
        )
    ]
    client = DummyClient(responses)
    monkeypatch.setattr(httpx, "Client", lambda *a, **k: client)
    twitch = TwitchClient("tok", "id")
    user = twitch.get_user_by_login("foo")
    assert user and user.login == "foo"
    assert user.broadcaster_type == BroadcasterType.PARTNER
    method, url, headers, params = client.requests[0]
    assert method == "GET" and url == TWITCH_USERS_URL
    assert params == {"login": "foo"}
    assert headers["Authorization"] == "Bearer tok"


def test_get_user_by_login_not_found(monkeypatch) -> None:
    responses = [DummyResponse({"data": []})]
    client = DummyClient(responses)
    monkeypatch.setattr(httpx, "Client", lambda *a, **k: client)
    twitch = TwitchClient("tok", "id")
    user = twitch.get_user_by_login("bar")
    assert user is None
