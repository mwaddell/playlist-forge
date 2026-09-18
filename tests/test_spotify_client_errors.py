from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import pytest

from playlist_forge import spotify_client
from playlist_forge.errors import AuthFailureError, ExternalServiceError
from playlist_forge.models import Playlist


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


def test_pull_playlist_tracks_handles_empty_playlist_response():
    class FakeSpotify:
        def playlist_items(self, _playlist_id, additional_types, fields):
            assert additional_types == ("track",)
            assert "items(" in fields
            return {"items": [], "next": None}

    playlist = Playlist(spotify_id="p1", name="Playlist")
    pulled = spotify_client.pull_playlist_tracks(FakeSpotify(), playlist, force=False)
    assert pulled == []


def test_pull_playlist_tracks_keeps_403_as_external_error_without_skip_flag(
    patched_spotify_exception,
):
    class FakeSpotify:
        def playlist_items(self, _playlist_id, additional_types, fields):
            assert additional_types == ("track",)
            assert "items(" in fields
            raise FakeSpotifyException(403)

    playlist = Playlist(spotify_id="p1", name="Owned Playlist")
    with pytest.raises(ExternalServiceError, match="status=403"):
        spotify_client.pull_playlist_tracks(FakeSpotify(), playlist, force=False)


def test_pull_library_warns_and_skips_for_playlist_permission_error(
    capsys, monkeypatch, patched_spotify_exception
):
    me_calls = {"count": 0}

    class FakeSpotify:
        def current_user(self):
            me_calls["count"] += 1
            return {"id": "me"}

    accessible = Playlist(spotify_id="p1", name="Accessible", owner_id="me")
    restricted = Playlist(spotify_id="p2", name="Restricted", owner_id="other-user")
    track = spotify_client.Track(
        spotify_id="track-1",
        title="Song",
        artist="Artist",
        album="Album",
        playlist_ids=[accessible.spotify_id],
        playlist_names=[accessible.name],
    )

    def fake_list_playlists(_spotify):
        return [accessible, restricted]

    def fake_pull_playlist_tracks(_spotify, playlist, force=False):
        if playlist.spotify_id == restricted.spotify_id:
            raise ExternalServiceError(
                "Spotify request failed while pulling tracks (status=403)."
            ) from FakeSpotifyException(403)
        return [track]

    monkeypatch.setattr(spotify_client, "list_playlists", fake_list_playlists)
    monkeypatch.setattr(spotify_client, "pull_playlist_tracks", fake_pull_playlist_tracks)
    pulled = spotify_client.pull_library(FakeSpotify())

    captured = capsys.readouterr()
    assert pulled == [track]
    assert me_calls["count"] == 1
    assert "Warning: Skipping playlist 'Restricted'" not in captured.out
    assert "Warning: Skipping playlist 'Restricted' (p2) due to permission error." in captured.err


def test_pull_library_does_not_lookup_current_user_without_permission_error(monkeypatch):
    me_calls = {"count": 0}

    class FakeSpotify:
        def current_user(self):
            me_calls["count"] += 1
            return {"id": "me"}

    playlist = Playlist(spotify_id="p1", name="Accessible", owner_id="me")
    track = spotify_client.Track(
        spotify_id="track-1",
        title="Song",
        artist="Artist",
        album="Album",
        playlist_ids=[playlist.spotify_id],
        playlist_names=[playlist.name],
    )

    monkeypatch.setattr(spotify_client, "list_playlists", lambda _spotify: [playlist])
    monkeypatch.setattr(
        spotify_client,
        "pull_playlist_tracks",
        lambda _spotify, _playlist, force=False: [track],
    )

    pulled = spotify_client.pull_library(FakeSpotify())

    assert pulled == [track]
    assert me_calls["count"] == 0


def test_pull_library_raises_external_error_when_current_user_id_is_unavailable(
    monkeypatch, patched_spotify_exception
):
    class FakeSpotify:
        def current_user(self):
            return {}

    playlist = Playlist(spotify_id="p1", name="Restricted", owner_id="other-user")

    monkeypatch.setattr(spotify_client, "list_playlists", lambda _spotify: [playlist])
    def fake_pull_playlist_tracks(_spotify, _playlist, force=False):
        raise ExternalServiceError(
            "Spotify request failed while pulling tracks (status=403)."
        ) from FakeSpotifyException(403)

    monkeypatch.setattr(spotify_client, "pull_playlist_tracks", fake_pull_playlist_tracks)

    with pytest.raises(ExternalServiceError, match="could not determine the current Spotify user id"):
        spotify_client.pull_library(FakeSpotify())


def test_playlist_matches_filter_checks_name_and_id():
    assert spotify_client.playlist_matches_filter("My Playlist", "abc123", ["playlist"])
    assert spotify_client.playlist_matches_filter("My Playlist", "37i9dQZF1DXcBWIGoYBM5M", ["BWIG"])
    assert not spotify_client.playlist_matches_filter("My Playlist", "abc123", ["other"])


def test_pull_library_filters_by_multiple_playlist_name_or_id_substrings(monkeypatch):
    class FakeSpotify:
        pass

    selected_by_name = Playlist(spotify_id="p1", name="Road Trip")
    selected_by_id = Playlist(spotify_id="37i9dQZF1DXcBWIGoYBM5M", name="Daily Mix")
    skipped = Playlist(spotify_id="p3", name="Focus")
    pulled_ids: list[str] = []

    def fake_pull_playlist_tracks(_spotify, playlist, force=False):
        pulled_ids.append(playlist.spotify_id)
        return []

    monkeypatch.setattr(
        spotify_client,
        "list_playlists",
        lambda _spotify: [selected_by_name, selected_by_id, skipped],
    )
    monkeypatch.setattr(spotify_client, "pull_playlist_tracks", fake_pull_playlist_tracks)

    spotify_client.pull_library(FakeSpotify(), playlist_filters=["Trip", "BWIG"])

    assert pulled_ids == ["p1", "37i9dQZF1DXcBWIGoYBM5M"]
