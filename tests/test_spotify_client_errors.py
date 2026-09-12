from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import pytest

from playlist_forge import spotify_client
from playlist_forge.errors import AuthFailureError


class FakeSpotifyException(Exception):
    def __init__(self, http_status: int, headers: dict | None = None):
        super().__init__(f"http_status={http_status}")
        self.http_status = http_status
        self.headers = headers or {}


@pytest.fixture
def patched_spotify_exception(monkeypatch):
    monkeypatch.setattr(spotify_client.spotipy.exceptions, "SpotifyException", FakeSpotifyException)


def test_search_track_retries_after_rate_limit(monkeypatch, patched_spotify_exception):
    calls = {"count": 0}

    class FakeSpotify:
        def search(self, q: str, type: str, limit: int):
            calls["count"] += 1
            if calls["count"] == 1:
                raise FakeSpotifyException(429, headers={"Retry-After": "0"})
            return {
                "tracks": {
                    "items": [
                        {
                            "id": "track-1",
                            "name": "Song",
                            "artists": [{"name": "Artist"}],
                            "album": {"name": "Album"},
                            "external_ids": {"isrc": "isrc-1"},
                            "popularity": 50,
                            "duration_ms": 200000,
                        }
                    ]
                }
            }

    monkeypatch.setattr(spotify_client.time, "sleep", lambda _seconds: None)
    track = spotify_client.search_track(FakeSpotify(), title="Song")

    assert calls["count"] == 2
    assert track is not None
    assert track.spotify_id == "track-1"


def test_list_playlists_raises_auth_failure_on_401(patched_spotify_exception):
    class FakeSpotify:
        def current_user_playlists(self, limit: int):
            raise FakeSpotifyException(401)

    with pytest.raises(AuthFailureError):
        spotify_client.list_playlists(FakeSpotify())


def test_retry_after_parses_http_date_header(monkeypatch):
    fixed_now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    future = fixed_now + timedelta(seconds=120)
    headers = {"Retry-After": format_datetime(future, usegmt=True)}

    class FixedDatetime:
        @staticmethod
        def now(tz):
            assert tz == timezone.utc
            return fixed_now

    monkeypatch.setattr(spotify_client, "datetime", FixedDatetime)
    delay = spotify_client._retry_after_seconds(headers)

    assert delay == 120.0
