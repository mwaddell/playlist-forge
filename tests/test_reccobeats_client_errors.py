from __future__ import annotations

import requests
import pytest

from playlist_forge import cache
from playlist_forge.errors import NetworkFailureError, RateLimitExceededError
from playlist_forge.reccobeats_client import ReccoBeatsClient


class DummySettings:
    config = {
        "reccobeats": {
            "base_url": "https://api.reccobeats.com",
            "request_delay_seconds": 0,
        }
    }
    reccobeats_api_key = None


class FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None, headers: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"status={self.status_code}")

    def json(self):
        return self._payload


def test_get_retries_timeout_then_succeeds(monkeypatch):
    client = ReccoBeatsClient(DummySettings())
    responses = [requests.exceptions.Timeout("timeout"), FakeResponse(200, {"tempo": 128})]

    def fake_get(*args, **kwargs):
        result = responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(client.session, "get", fake_get)
    monkeypatch.setattr("playlist_forge.reccobeats_client.time.sleep", lambda _seconds: None)

    payload = client._get("/v1/audio-features", {"ids": "abc"})
    assert payload == {"tempo": 128}


def test_get_raises_after_repeated_rate_limits(monkeypatch):
    client = ReccoBeatsClient(DummySettings())

    def fake_get(*args, **kwargs):
        return FakeResponse(429, headers={"Retry-After": "0"})

    monkeypatch.setattr(client.session, "get", fake_get)
    monkeypatch.setattr("playlist_forge.reccobeats_client.time.sleep", lambda _seconds: None)

    with pytest.raises(RateLimitExceededError):
        client._get("/v1/audio-features", {"ids": "abc"})


def test_get_retries_with_lowercase_retry_after_header(monkeypatch):
    client = ReccoBeatsClient(DummySettings())
    slept: list[float] = []
    responses = [
        FakeResponse(429, headers={"retry-after": "0.25"}),
        FakeResponse(200, {"tempo": 128}),
    ]

    def fake_get(*args, **kwargs):
        return responses.pop(0)

    monkeypatch.setattr(client.session, "get", fake_get)
    monkeypatch.setattr("playlist_forge.reccobeats_client.time.sleep", lambda seconds: slept.append(seconds))

    payload = client._get("/v1/audio-features", {"ids": "abc"})

    assert payload == {"tempo": 128}
    assert slept == [0.25]


def test_fetch_does_not_cache_transient_failure(monkeypatch):
    client = ReccoBeatsClient(DummySettings())
    cache_writes: list[tuple[str, dict]] = []

    monkeypatch.setattr(cache, "get", lambda key: None)
    monkeypatch.setattr(cache, "set", lambda key, value: cache_writes.append((key, value)))
    monkeypatch.setattr(client, "_get", lambda _path, _params: (_ for _ in ()).throw(NetworkFailureError("boom")))

    with pytest.raises(NetworkFailureError):
        client.fetch_by_spotify_id("abc")

    assert cache_writes == []
