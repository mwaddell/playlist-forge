from datetime import datetime, timezone

import requests
from spotipy import SpotifyException

from playlist_forge import rate_limit
from playlist_forge.config import Settings
from playlist_forge.reccobeats_client import ReccoBeatsClient
from playlist_forge.spotify_client import _paginate, _spotify_request


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
        result = next(self._responses)
        if isinstance(result, Exception):
            raise result
        return result


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


def test_paginate_retries_same_page_after_rate_limit(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr("playlist_forge.spotify_client.time.sleep", sleeps.append)

    first_page = {"items": [{"id": "page-1"}], "next": "more"}
    second_page = {"items": [{"id": "page-2"}], "next": None}
    calls: list[dict] = []

    class FakeSpotify:
        def __init__(self):
            self.attempts = 0

        def next(self, page: dict) -> dict:
            self.attempts += 1
            calls.append(page)
            if self.attempts == 1:
                raise SpotifyException(429, -1, "rate limited", headers={"Retry-After": "1"})
            return second_page

    assert _paginate(FakeSpotify(), first_page) == [{"id": "page-1"}, {"id": "page-2"}]
    assert calls == [first_page, first_page]
    assert sleeps == [1.0]


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


def test_reccobeats_get_retries_http_error_rate_limit(monkeypatch):
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
    rate_limited = FakeResponse(429, headers={"Retry-After": "2"})
    client.session = FakeSession(
        [
            requests.HTTPError("429 error", response=rate_limited),
            FakeResponse(200, payload={"tempo": 101.0}),
        ]
    )

    assert client._get("/v1/audio-features", {"ids": "spotify-track-id"}) == {"tempo": 101.0}
    assert sleeps == [2.0]


def test_retry_delay_seconds_supports_http_date_retry_after(monkeypatch):
    class FrozenDateTime:
        @staticmethod
        def now(_tz: timezone) -> datetime:
            return datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    monkeypatch.setattr(rate_limit, "datetime", FrozenDateTime)

    assert (
        rate_limit.retry_delay_seconds("Thu, 01 Jan 2026 12:00:05 GMT", attempt=0) == 5.0
    )


def test_retry_delay_seconds_falls_back_for_invalid_retry_after():
    assert rate_limit.retry_delay_seconds("not-a-delay", attempt=2) == 4.0


def test_retry_delay_seconds_clamps_past_http_date_to_zero(monkeypatch):
    class FrozenDateTime:
        @staticmethod
        def now(_tz: timezone) -> datetime:
            return datetime(2026, 1, 1, 12, 0, 10, tzinfo=timezone.utc)

    monkeypatch.setattr(rate_limit, "datetime", FrozenDateTime)

    assert rate_limit.retry_delay_seconds("Thu, 01 Jan 2026 12:00:05 GMT", attempt=0) == 0.0
