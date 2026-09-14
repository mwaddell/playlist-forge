"""Merge two or more existing playlists into one new playlist."""

from __future__ import annotations

import spotipy

from .. import spotify_client


def merge(
    spotify: spotipy.Spotify,
    playlist_names: list[str],
    into_name: str,
    dedupe_by_isrc: bool = True,
    dry_run: bool = False,
) -> str | None:
    """Merge tracks from existing playlists into a new playlist.

    Args:
        spotify: Authenticated Spotify API client.
        playlist_names: Source playlist names to merge.
        into_name: Name for the new merged playlist.
        dedupe_by_isrc: Whether to drop duplicate ISRC matches.
        dry_run: Whether to skip API writes and only print actions.

    Returns:
        Created playlist ID, or None in dry-run mode.
    """
    all_playlists = spotify_client.list_playlists(spotify)
    targets = [p for p in all_playlists if p.name in playlist_names]
    missing = set(playlist_names) - {p.name for p in targets}
    if missing:
        raise ValueError(f"Playlist(s) not found: {', '.join(missing)}")

    seen_isrc: set[str] = set()
    seen_ids: set[str] = set()
    track_ids: list[str] = []

    for playlist in targets:
        for t in spotify_client.pull_playlist_tracks(spotify, playlist):
            if t.spotify_id in seen_ids:
                continue
            if dedupe_by_isrc and t.isrc and t.isrc in seen_isrc:
                continue
            seen_ids.add(t.spotify_id)
            if t.isrc:
                seen_isrc.add(t.isrc)
            track_ids.append(t.spotify_id)

    return spotify_client.create_playlist(
        spotify, into_name, track_ids,
        description=f"Merged from: {', '.join(playlist_names)}",
        dry_run=dry_run,
    )
