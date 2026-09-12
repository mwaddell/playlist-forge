"""Thin wrapper around spotipy for the operations playlist-forge needs.

Keeps all direct Spotify API calls in one place so rate limiting, pagination,
and error handling are handled consistently, and so `analyze/*` never has to
import spotipy at all.
"""

from __future__ import annotations

import time

import spotipy
from rich.progress import track as progress_track

from .models import Playlist, Track


def _paginate(spotify: spotipy.Spotify, first_page: dict) -> list[dict]:
    items = list(first_page["items"])
    page = first_page
    while page.get("next"):
        page = spotify.next(page)
        items.extend(page["items"])
    return items


def list_playlists(spotify: spotipy.Spotify) -> list[Playlist]:
    first = spotify.current_user_playlists(limit=50)
    raw = _paginate(spotify, first)
    return [
        Playlist(
            spotify_id=p["id"],
            name=p["name"],
            description=p.get("description") or None,
            track_count=p["tracks"]["total"],
            owner=p["owner"]["display_name"],
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
        resp = spotify.artists(batch)
        for artist in resp["artists"]:
            if artist:
                genre_map[artist["id"]] = artist.get("genres", [])
        time.sleep(0.05)
    return genre_map


def pull_playlist_tracks(
    spotify: spotipy.Spotify,
    playlist: Playlist,
    fetch_genres: bool = True,
) -> list[Track]:
    first = spotify.playlist_items(
        playlist.spotify_id,
        additional_types=("track",),
        fields=(
            "items(added_at,track(id,name,album(name,release_date),artists(id,name),"
            "duration_ms,popularity,external_ids)),next"
        ),
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
    """Pull every playlist (optionally filtered by name substring) and merge
    tracks that appear in multiple playlists into a single record with a
    combined playlist_ids / playlist_names list.
    """
    playlists = list_playlists(spotify)
    if playlist_name_filter:
        playlists = [p for p in playlists if playlist_name_filter.lower() in p.name.lower()]

    by_id: dict[str, Track] = {}
    for playlist in progress_track(playlists, description="Pulling playlists..."):
        for t in pull_playlist_tracks(spotify, playlist):
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
    """Best-effort match of a plain-text (title, artist, album) to a Spotify track."""
    query_parts = [f"track:{title}"]
    if artist:
        query_parts.append(f"artist:{artist}")
    if album:
        query_parts.append(f"album:{album}")
    query = " ".join(query_parts)

    results = spotify.search(q=query, type="track", limit=5)
    items = results.get("tracks", {}).get("items", [])
    if not items:
        # fall back to a looser, unscoped query
        loose_query = " ".join(p for p in (title, artist) if p)
        results = spotify.search(q=loose_query, type="track", limit=5)
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
    if dry_run:
        print(f"[dry-run] Would create playlist '{name}' with {len(track_ids)} tracks.")
        return None

    me = spotify.current_user()
    playlist = spotify.user_playlist_create(
        me["id"], name, public=public, description=description
    )
    for i in range(0, len(track_ids), 100):  # API caps add_items at 100/request
        spotify.playlist_add_items(playlist["id"], track_ids[i : i + 100])
    return playlist["id"]


def add_tracks(
    spotify: spotipy.Spotify, playlist_id: str, track_ids: list[str], dry_run: bool = False
) -> None:
    if dry_run:
        print(f"[dry-run] Would add {len(track_ids)} tracks to playlist {playlist_id}.")
        return
    for i in range(0, len(track_ids), 100):
        spotify.playlist_add_items(playlist_id, track_ids[i : i + 100])
