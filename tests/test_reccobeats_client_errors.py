from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import pytest
import requests

from playlist_forge import cache
from playlist_forge.errors import NetworkFailureError, RateLimitExceededError
from playlist_forge.models import Track
from playlist_forge.reccobeats_client import ReccoBeatsClient, _fallback_progress_track


class DummySettings:
    config = {
        "reccobeats": {
            "base_url": "https://api.reccobeats.com",
            "request_delay_seconds": 0,
        }
    }
    reccobeats_api_key = None


class DummySettingsWithApiKey(DummySettings):
    reccobeats_api_key = "test-key"


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
    monkeypatch.setattr(
        "playlist_forge.reccobeats_client.time.sleep",
        lambda seconds: slept.append(seconds),
    )

    payload = client._get("/v1/audio-features", {"ids": "abc"})

    assert payload == {"tempo": 128}
    assert slept == [0.25]


def test_retry_after_parses_http_date_header(monkeypatch):
    fixed_now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    future = fixed_now + timedelta(seconds=120)
    resp = FakeResponse(429, headers={"Retry-After": format_datetime(future, usegmt=True)})

    class FixedDatetime:
        @staticmethod
        def now(tz):
            assert tz == timezone.utc
            return fixed_now

    monkeypatch.setattr("playlist_forge.reccobeats_client.datetime", FixedDatetime)
    delay = ReccoBeatsClient._retry_after_seconds(resp)

    assert delay == 120.0


def test_sets_bearer_auth_header_when_api_key_present():
    client = ReccoBeatsClient(DummySettingsWithApiKey())
    assert client.session.headers["Authorization"] == (
        "Bearer " + DummySettingsWithApiKey.reccobeats_api_key
    )


def test_fetch_does_not_cache_transient_failure(monkeypatch):
    client = ReccoBeatsClient(DummySettings())
    cache_writes: list[tuple[str, dict]] = []

    def raise_network_failure(*_args, **_kwargs):
        raise NetworkFailureError("boom")

    monkeypatch.setattr(cache, "get", lambda key: None)
    monkeypatch.setattr(cache, "set", lambda key, value: cache_writes.append((key, value)))
    monkeypatch.setattr(client, "_get", raise_network_failure)

    with pytest.raises(NetworkFailureError):
        client.fetch_by_spotify_id("abc")

    assert cache_writes == []


def test_enrich_uses_progress_indicator(monkeypatch):
    client = ReccoBeatsClient(DummySettings())
    descriptions: list[str] = []
    tracks = [
        Track(spotify_id="track-1", title="Song 1", artist="Artist 1", album="Album 1"),
        Track(spotify_id="track-2", title="Song 2", artist="Artist 2", album="Album 2"),
    ]

    monkeypatch.setattr("playlist_forge.reccobeats_client.sys.stdout.isatty", lambda: True)
    monkeypatch.setattr(
        "playlist_forge.reccobeats_client.progress_track",
        lambda items, description: descriptions.append(description) or iter(items),
    )
    monkeypatch.setattr(client, "fetch_by_spotify_id", lambda spotify_id: {"tempo": 123.0, "confidence": 0.9})

    enriched = client.enrich(tracks)

    assert descriptions == ["Enriching tracks..."]
    assert enriched is tracks
    assert all(track.feature_source == "reccobeats" for track in tracks)


def test_enrich_skips_progress_indicator_without_tty(monkeypatch):
    client = ReccoBeatsClient(DummySettings())
    tracks = [Track(spotify_id="track-1", title="Song 1", artist="Artist 1", album="Album 1")]

    monkeypatch.setattr("playlist_forge.reccobeats_client.sys.stdout.isatty", lambda: False)
    monkeypatch.setattr(
        "playlist_forge.reccobeats_client.progress_track",
        lambda *_args, **_kwargs: pytest.fail("progress_track should not run without a TTY"),
    )
    monkeypatch.setattr(client, "fetch_by_spotify_id", lambda spotify_id: None)

    enriched = client.enrich(tracks)

    assert enriched is tracks
    assert tracks[0].feature_source == "unmatched"


def test_enrich_skips_progress_indicator_when_stdout_has_no_isatty(monkeypatch):
    client = ReccoBeatsClient(DummySettings())
    tracks = [Track(spotify_id="track-1", title="Song 1", artist="Artist 1", album="Album 1")]

    class StdoutWithoutIsatty:
        def write(self, _text):
            return None

        def flush(self):
            return None

    monkeypatch.setattr("playlist_forge.reccobeats_client.sys.stdout", StdoutWithoutIsatty())
    monkeypatch.setattr(
        "playlist_forge.reccobeats_client.progress_track",
        lambda *_args, **_kwargs: pytest.fail("progress_track should not run without isatty"),
    )
    monkeypatch.setattr(client, "fetch_by_spotify_id", lambda spotify_id: None)

    enriched = client.enrich(tracks)

    assert enriched is tracks
    assert tracks[0].feature_source == "unmatched"


def test_fallback_progress_track_returns_iterator():
    items = [1, 2, 3]

    progress_iter = _fallback_progress_track(items, description="Enriching tracks...", total=3)

    assert list(progress_iter) == items
