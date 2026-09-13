"""Thin wrapper around spotipy for the operations playlist-forge needs.

Keeps all direct Spotify API calls in one place so rate limiting, pagination,
and error handling are handled consistently, and so `analyze/*` never has to
import spotipy at all.
"""

from __future__ import annotations

import sys
import time
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import TypeVar

import requests
import spotipy
from rich.progress import track as progress_track

from .errors import (
    AuthFailureError,
    ExternalServiceError,
    NetworkFailureError,
    PlaylistPermissionError,
    RateLimitExceededError,
)
from .models import Playlist, Track

T = TypeVar("T")


def _spotify_status_code(exc: spotipy.exceptions.SpotifyException) -> int | None:
    for attr in ("http_status", "status_code", "code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    return None


def _spotify_headers(exc: spotipy.exceptions.SpotifyException) -> Mapping[str, object] | None:
    for attr in ("headers", "http_headers"):
        value = getattr(exc, attr, None)
        if isinstance(value, Mapping):
            return value
    return None


_SPOTIFY_MAX_RETRIES = 3
_SPOTIFY_BASE_BACKOFF_SECONDS = 1.0


def _retry_after_seconds(headers: dict | None) -> float | None:
    if not headers:
        return None
    raw = headers.get("Retry-After") or headers.get("retry-after")
    if not raw:
        return None
    try:
        return max(float(raw), 0.0)
    except (TypeError, ValueError):
        pass
    try:
        retry_at = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=timezone.utc)
    return max((retry_at - datetime.now(timezone.utc)).total_seconds(), 0.0)


def _spotify_request(
    operation: Callable[[], T],
    description: str,
    *,
    max_retries: int = _SPOTIFY_MAX_RETRIES,
) -> T:
    for attempt in range(max_retries + 1):
        try:
            return operation()
        except spotipy.exceptions.SpotifyException as exc:
            if _spotify_status_code(exc) != 429 or attempt >= max_retries:
                raise
            delay = _retry_after_seconds(_spotify_headers(exc)) or (
                _SPOTIFY_BASE_BACKOFF_SECONDS * (2**attempt)
            )
            print(f"[spotify] rate limited during {description}; retrying in {delay:.2f}s")
            time.sleep(delay)

    raise RuntimeError(f"unreachable retry loop for {description}")


def _spotify_call(
    operation: str,
    call: Callable[[], T],
    *,
    forbidden_message: str | None = None,
) -> T:
    for attempt in range(_SPOTIFY_MAX_RETRIES + 1):
        try:
            return call()
        except spotipy.exceptions.SpotifyException as exc:
            status = _spotify_status_code(exc)
            headers = _spotify_headers(exc)
            if status == 403 and forbidden_message is not None:
                raise PlaylistPermissionError(forbidden_message) from exc
            if status == 401:
                raise AuthFailureError(
                    "Spotify authentication failed (401). "
                    "Run `playlist-forge auth login` and retry."
                ) from exc
            if status == 429:
                if attempt >= _SPOTIFY_MAX_RETRIES:
                    raise RateLimitExceededError(
                        "Spotify rate limit persisted after retries. Please wait and try again."
                    ) from exc
                delay = _retry_after_seconds(headers) or (
                    _SPOTIFY_BASE_BACKOFF_SECONDS * (2**attempt)
                )
                time.sleep(delay)
                continue
            if status and status >= 500 and attempt < _SPOTIFY_MAX_RETRIES:
                time.sleep(_SPOTIFY_BASE_BACKOFF_SECONDS * (2**attempt))
                continue
            raise ExternalServiceError(
                f"Spotify request failed while {operation} (status={status})."
            ) from exc
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
            if attempt >= _SPOTIFY_MAX_RETRIES:
                raise NetworkFailureError(
                    "Spotify request timed out or lost connection after retries."
                ) from exc
            time.sleep(_SPOTIFY_BASE_BACKOFF_SECONDS * (2**attempt))
        except requests.exceptions.RequestException as exc:
            raise NetworkFailureError(f"Spotify request failed while {operation}: {exc}") from exc

    raise NetworkFailureError(f"Spotify request failed while {operation}.")


def _paginate(spotify: spotipy.Spotify, first_page: dict) -> list[dict]:
    items = list(first_page["items"])
    page = first_page
    while page.get("next"):
        page = _spotify_call("paginating Spotify response", lambda: spotify.next(page))
        items.extend(page["items"])
    return items


def list_playlists(spotify: spotipy.Spotify) -> list[Playlist]:
    """List the current user's playlists.

    Args:
        spotify: Authenticated Spotify API client.

    Returns:
        Playlist records visible to the current user.
    """
    first = _spotify_call("listing playlists", lambda: spotify.current_user_playlists(limit=50))
    raw = _paginate(spotify, first)
    return [
        Playlist(
            spotify_id=p["id"],
            name=p["name"],
            description=p.get("description") or None,
            track_count=p["tracks"]["total"],
            owner=p["owner"]["display_name"],
            owner_id=p["owner"].get("id"),
            is_collaborative=p.get("collaborative", False),
        )
        for p in raw
        if p is not None
    ]


def _artist_genre_map(spotify: spotipy.Spotify, artist_ids: set[str]) -> dict[str, list[str]]:
    """Batch-fetch genres for a set of artist IDs (max 50 per request)."""
    genre_map: dict[str, list[str]] = {}
    ids = list(artist_ids)
    for i in range(0, len(ids), 50):
        batch = ids[i : i + 50]
        resp = _spotify_call("fetching artist genres", lambda: spotify.artists(batch))
        for artist in resp["artists"]:
            if artist:
                genre_map[artist["id"]] = artist.get("genres", [])
        time.sleep(0.05)
    return genre_map


def pull_playlist_tracks(
    spotify: spotipy.Spotify,
    playlist: Playlist,
    fetch_genres: bool = True,
    skip_permission_errors: bool = False,
) -> list[Track]:
    """Pull all tracks for one playlist.

    Args:
        spotify: Authenticated Spotify API client.
        playlist: Playlist metadata to fetch tracks from.
        fetch_genres: Whether to fetch artist genres for included artists.
        skip_permission_errors: Whether to convert playlist-item 403 responses into
            skip-friendly permission errors.

    Returns:
        Track objects for the playlist.
    """
    first = _spotify_call(
        f"pulling tracks for playlist '{playlist.name}'",
        lambda: spotify.playlist_items(
            playlist.spotify_id,
            additional_types=("track",),
            fields=(
                "items(added_at,track(id,name,album(name,release_date),artists(id,name),"
                "duration_ms,popularity,external_ids)),next"
            ),
        ),
        forbidden_message=(
            f"Skipping playlist '{playlist.name}' ({playlist.spotify_id}) due to permission error."
        )
        if skip_permission_errors
        else None,
    )
    raw_items = _paginate(spotify, first)

    tracks: list[Track] = []
    artist_ids: set[str] = set()
    for item in raw_items:
        t = item.get("track")
        if not t or not t.get("id"):
            continue  # local files / removed tracks have no id
        for a in t.get("artists", []):
            artist_ids.add(a["id"])

    genre_map = _artist_genre_map(spotify, artist_ids) if fetch_genres and artist_ids else {}

    for item in raw_items:
        t = item.get("track")
        if not t or not t.get("id"):
            continue
        artists = t.get("artists", [])
        primary_artist = artists[0] if artists else {"id": None, "name": "Unknown"}
        genres: list[str] = []
        for a in artists:
            genres.extend(genre_map.get(a["id"], []))

        release_date = (t.get("album") or {}).get("release_date", "")
        year = None
        if release_date:
            try:
                year = int(release_date[:4])
            except ValueError:
                year = None

        tracks.append(
            Track(
                spotify_id=t["id"],
                title=t["name"],
                artist=primary_artist["name"],
                album=(t.get("album") or {}).get("name", ""),
                playlist_ids=[playlist.spotify_id],
                playlist_names=[playlist.name],
                isrc=(t.get("external_ids") or {}).get("isrc"),
                year=year,
                popularity=t.get("popularity"),
                duration_ms=t.get("duration_ms"),
                added_at=item.get("added_at"),
                artist_genres=sorted(set(genres)),
            )
        )
    return tracks


def pull_library(spotify: spotipy.Spotify, playlist_name_filter: str | None = None) -> list[Track]:
    """Pull playlists and merge duplicate track IDs across playlists.

    Args:
        spotify: Authenticated Spotify API client.
        playlist_name_filter: Optional case-insensitive playlist name substring filter.

    Returns:
        Unique tracks with combined playlist membership fields.
    """
    playlists = list_playlists(spotify)
    if playlist_name_filter:
        playlists = [p for p in playlists if playlist_name_filter.lower() in p.name.lower()]

    by_id: dict[str, Track] = {}
    current_user_id: str | None = None
    for playlist in progress_track(playlists, description="Pulling playlists..."):
        try:
            playlist_tracks = pull_playlist_tracks(
                spotify,
                playlist,
                skip_permission_errors=bool(playlist.owner_id),
            )
        except PlaylistPermissionError as exc:
            if current_user_id is None:
                current_user_id = _spotify_call(
                    "loading current Spotify user",
                    lambda: spotify.me(),
                ).get("id")
            if playlist.owner_id and current_user_id and playlist.owner_id != current_user_id:
                print(f"Warning: {exc}", file=sys.stderr)
                continue
            cause = exc.__cause__
            status = _spotify_status_code(cause) if isinstance(cause, spotipy.exceptions.SpotifyException) else 403
            raise ExternalServiceError(
                f"Spotify request failed while pulling tracks for playlist '{playlist.name}' "
                f"(status={status})."
            ) from (cause if isinstance(cause, Exception) else exc)
        for t in playlist_tracks:
            existing = by_id.get(t.spotify_id)
            if existing:
                existing.playlist_ids.extend(t.playlist_ids)
                existing.playlist_names.extend(t.playlist_names)
            else:
                by_id[t.spotify_id] = t

    return list(by_id.values())


def search_track(
    spotify: spotipy.Spotify, title: str, artist: str = "", album: str = ""
) -> Track | None:
    """Best-effort match of plain text fields to a Spotify track.

    Args:
        spotify: Authenticated Spotify API client.
        title: Track title query.
        artist: Optional artist query.
        album: Optional album query.

    Returns:
        A matched Track when found, otherwise None.
    """
    query_parts = [f"track:{title}"]
    if artist:
        query_parts.append(f"artist:{artist}")
    if album:
        query_parts.append(f"album:{album}")
    query = " ".join(query_parts)

    results = _spotify_call(
        "searching for track", lambda: spotify.search(q=query, type="track", limit=5)
    )
    items = results.get("tracks", {}).get("items", [])
    if not items:
        # fall back to a looser, unscoped query
        loose_query = " ".join(p for p in (title, artist) if p)
        results = _spotify_call(
            "running fallback track search",
            lambda: spotify.search(q=loose_query, type="track", limit=5),
        )
        items = results.get("tracks", {}).get("items", [])
    if not items:
        return None

    t = items[0]
    return Track(
        spotify_id=t["id"],
        title=t["name"],
        artist=t["artists"][0]["name"] if t["artists"] else "",
        album=(t.get("album") or {}).get("name", ""),
        isrc=(t.get("external_ids") or {}).get("isrc"),
        popularity=t.get("popularity"),
        duration_ms=t.get("duration_ms"),
    )


def create_playlist(
    spotify: spotipy.Spotify,
    name: str,
    track_ids: list[str],
    description: str = "",
    public: bool = False,
    dry_run: bool = False,
) -> str | None:
    """Create a playlist and add the provided tracks.

    Args:
        spotify: Authenticated Spotify API client.
        name: Playlist name to create.
        track_ids: Spotify track IDs to add.
        description: Playlist description text.
        public: Whether the playlist should be public.
        dry_run: Whether to skip API writes and only print actions.

    Returns:
        The created playlist ID, or None for dry-run mode.
    """
    if dry_run:
        print(f"[dry-run] Would create playlist '{name}' with {len(track_ids)} tracks.")
        return None

    me = _spotify_call("reading current Spotify user", spotify.current_user)
    playlist = _spotify_call(
        f"creating playlist '{name}'",
        lambda: spotify.user_playlist_create(
            me["id"], name, public=public, description=description
        ),
    )
    for i in range(0, len(track_ids), 100):  # API caps add_items at 100/request
        _spotify_call(
            f"adding tracks to playlist '{name}'",
            lambda: spotify.playlist_add_items(playlist["id"], track_ids[i : i + 100]),
        )
    return playlist["id"]


def add_tracks(
    spotify: spotipy.Spotify, playlist_id: str, track_ids: list[str], dry_run: bool = False
) -> None:
    """Add tracks to an existing playlist in API-sized batches.

    Args:
        spotify: Authenticated Spotify API client.
        playlist_id: Spotify playlist ID to update.
        track_ids: Spotify track IDs to append.
        dry_run: Whether to skip API writes and only print actions.

    Returns:
        None.
    """
    if dry_run:
        print(f"[dry-run] Would add {len(track_ids)} tracks to playlist {playlist_id}.")
        return
    for i in range(0, len(track_ids), 100):
        _spotify_call(
            f"adding tracks to playlist '{playlist_id}'",
            lambda: spotify.playlist_add_items(playlist_id, track_ids[i : i + 100]),
        )
