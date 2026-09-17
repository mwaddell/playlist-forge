from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import pytest
import requests

from playlist_forge import cache
from playlist_forge.errors import (
    ConfigurationError,
    NetworkFailureError,
    RateLimitExceededError,
)
from playlist_forge.getgenre_client import GetGenreClient, _fallback_progress_track
from playlist_forge.models import Track


class DummySettings:
    config = {
        "getgenre": {
            "base_url": "https://api.getgenre.com",
            "request_delay_seconds": 0,
            "timeout_seconds": 10,
        }
    }
    getgenre_username = "user@example.com"
    getgenre_password = "super-secret"


class MissingCredentialSettings(DummySettings):
    getgenre_username = None
    getgenre_password = None


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


def test_authenticate_requires_credentials():
    client = GetGenreClient(MissingCredentialSettings())

    with pytest.raises(ConfigurationError, match="GetGenre credentials are not configured"):
        client._authenticate()


def test_get_retries_with_lowercase_retry_after_header(monkeypatch):
    client = GetGenreClient(DummySettings())
    slept: list[float] = []
    auth_calls: list[dict] = []
    responses = [
        FakeResponse(429, headers={"retry-after": "0.25"}),
        FakeResponse(200, {"top_genres": ["indie"], "genres": ["indie", "rock"]}),
    ]

    monkeypatch.setattr(client.session, "post", lambda *args, **kwargs: auth_calls.append(kwargs) or FakeResponse(
        200, {"access_token": "token", "token_type": "Bearer"}
    ))
    monkeypatch.setattr(client.session, "get", lambda *args, **kwargs: responses.pop(0))
    monkeypatch.setattr("playlist_forge.getgenre_client.time.sleep", lambda seconds: slept.append(seconds))

    payload = client._get({"album_name": "Album", "artist_name": "Artist", "timeout": 10})

    assert payload == {"top_genres": ["indie"], "genres": ["indie", "rock"]}
    assert slept == [0.25]
    assert auth_calls


def test_retry_after_parses_http_date_header(monkeypatch):
    fixed_now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    future = fixed_now + timedelta(seconds=120)
    resp = FakeResponse(429, headers={"Retry-After": format_datetime(future, usegmt=True)})

    class FixedDatetime:
        @staticmethod
        def now(tz):
            assert tz == timezone.utc
            return fixed_now

    monkeypatch.setattr("playlist_forge.getgenre_client.datetime", FixedDatetime)
    delay = GetGenreClient._retry_after_seconds(resp)

    assert delay == 120.0


def test_fetch_does_not_cache_transient_failure(monkeypatch):
    client = GetGenreClient(DummySettings())
    cache_writes: list[tuple[str, dict]] = []

    def raise_network_failure(*_args, **_kwargs):
        raise NetworkFailureError("boom")

    monkeypatch.setattr(cache, "get", lambda typ, key: None)
    monkeypatch.setattr(cache, "set", lambda typ, key, value: cache_writes.append((key, value)))
    monkeypatch.setattr(client, "_get", raise_network_failure)

    with pytest.raises(NetworkFailureError):
        client.fetch("Album", "Artist")

    assert cache_writes == []


def test_fetch_caches_not_found_results(monkeypatch):
    client = GetGenreClient(DummySettings())
    writes: list[tuple[cache.CacheType, str, dict]] = []

    monkeypatch.setattr(cache, "get", lambda typ, key: None)
    monkeypatch.setattr(cache, "set", lambda typ, key, value: writes.append((typ, key, value)))
    monkeypatch.setattr(client, "_get", lambda _params: None)
    monkeypatch.setattr("playlist_forge.getgenre_client.time.sleep", lambda _seconds: None)

    assert client.fetch("Album", "Artist") is None
    assert writes == [(cache.CacheType.GETGENRE, "getgenre:album:artist", {})]


def test_enrich_clears_stale_getgenre_match_when_no_genres_found(monkeypatch):
    client = GetGenreClient(DummySettings())
    tracks = [
        Track(
            spotify_id="track-1",
            title="Song 1",
            artist="Artist 1",
            album="Album 1",
            genres=["stale"],
            genre_source="getgenre",
        )
    ]

    monkeypatch.setattr(client, "fetch", lambda album, artist: {})

    enriched = client.enrich(tracks)

    assert enriched is tracks
    assert tracks[0].genres == []
    assert tracks[0].genre_source == "unmatched"


def test_enrich_uses_progress_indicator(monkeypatch):
    client = GetGenreClient(DummySettings())
    descriptions: list[str] = []
    tracks = [
        Track(spotify_id="track-1", title="Song 1", artist="Artist 1", album="Album 1"),
        Track(spotify_id="track-2", title="Song 2", artist="Artist 2", album="Album 2"),
    ]

    monkeypatch.setattr("playlist_forge.getgenre_client.sys.stdout.isatty", lambda: True)
    monkeypatch.setattr(
        "playlist_forge.getgenre_client.progress_track",
        lambda items, description: descriptions.append(description) or iter(items),
    )
    monkeypatch.setattr(
        client,
        "fetch",
        lambda album, artist: {"top_genres": ["indie"], "genres": ["indie"]},
    )

    enriched = client.enrich(tracks)

    assert descriptions == ["Enriching tracks..."]
    assert enriched is tracks
    assert all(track.genre_source.startswith("getgenre") for track in tracks)


def test_fallback_progress_track_returns_iterator():
    items = [1, 2, 3]

    progress_iter = _fallback_progress_track(items, description="Enriching tracks...", total=3)

    assert list(progress_iter) == items


def test_get_raises_after_repeated_rate_limits(monkeypatch):
    client = GetGenreClient(DummySettings())

    monkeypatch.setattr(client.session, "post", lambda *args, **kwargs: FakeResponse(
        200, {"access_token": "token", "token_type": "Bearer"}
    ))
    monkeypatch.setattr(client.session, "get", lambda *args, **kwargs: FakeResponse(429, headers={"Retry-After": "0"}))
    monkeypatch.setattr("playlist_forge.getgenre_client.time.sleep", lambda _seconds: None)

    with pytest.raises(RateLimitExceededError):
        client._get({"artist_name": "Artist", "timeout": 10})
