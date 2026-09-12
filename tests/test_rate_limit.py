import requests
from spotipy import SpotifyException

from playlist_forge.config import Settings
from playlist_forge.reccobeats_client import ReccoBeatsClient
from playlist_forge.spotify_client import _spotify_request


class FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None, headers: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = headers or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error", response=self)

    def json(self) -> dict:
        return self._payload


class FakeSession:
    def __init__(self, responses: list[FakeResponse]):
        self._responses = iter(responses)

    def get(self, *_args, **_kwargs) -> FakeResponse:
        return next(self._responses)


def test_spotify_request_retries_using_retry_after(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr("playlist_forge.spotify_client.time.sleep", sleeps.append)

    attempts = 0

    def operation() -> dict:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise SpotifyException(429, -1, "rate limited", headers={"Retry-After": "2"})
        return {"ok": True}

    assert _spotify_request(operation, "test request") == {"ok": True}
    assert attempts == 2
    assert sleeps == [2.0]


def test_reccobeats_get_retries_using_retry_after(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr("playlist_forge.reccobeats_client.time.sleep", sleeps.append)

    settings = Settings(
        spotify_client_id=None,
        spotify_client_secret=None,
        spotify_redirect_uri="http://127.0.0.1:8080/callback",
        reccobeats_api_key=None,
        config={
            "reccobeats": {
                "base_url": "https://api.reccobeats.test",
                "request_delay_seconds": 0,
            }
        },
    )
    client = ReccoBeatsClient(settings)
    client.session = FakeSession(
        [
            FakeResponse(429, headers={"Retry-After": "3"}),
            FakeResponse(200, payload={"tempo": 120.0}),
        ]
    )

    assert client._get("/v1/audio-features", {"ids": "spotify-track-id"}) == {"tempo": 120.0}
    assert sleeps == [3.0]


def test_reccobeats_get_uses_case_insensitive_retry_after(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr("playlist_forge.reccobeats_client.time.sleep", sleeps.append)

    settings = Settings(
        spotify_client_id=None,
        spotify_client_secret=None,
        spotify_redirect_uri="http://127.0.0.1:8080/callback",
        reccobeats_api_key=None,
        config={
            "reccobeats": {
                "base_url": "https://api.reccobeats.test",
                "request_delay_seconds": 0,
            }
        },
    )
    client = ReccoBeatsClient(settings)
    client.session = FakeSession(
        [
            FakeResponse(429, headers={"retry-after": "4"}),
            FakeResponse(200, payload={"tempo": 98.0}),
        ]
    )

    assert client._get("/v1/audio-features", {"ids": "spotify-track-id"}) == {"tempo": 98.0}
    assert sleeps == [4.0]
