"""Resolve a plain-text list of songs (title/artist/album) to Spotify tracks
and add the matches to a playlist.

Input file format is one song per line, fields separated by a delimiter the
user specifies (default ';'), e.g.:

    Everything In Its Right Place;Radiohead;Kid A
    Kid A;Radiohead
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import spotipy

from .. import spotify_client
from ..models import Track


@dataclass
class MatchResult:
    query: str
    matched: Track | None
    confidence_note: str


def parse_text_list(path: str | Path, field_delimiter: str = ";") -> list[dict]:
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split(field_delimiter)]
        row = {"title": parts[0]}
        if len(parts) > 1:
            row["artist"] = parts[1]
        if len(parts) > 2:
            row["album"] = parts[2]
        rows.append(row)
    return rows


def match_all(spotify: spotipy.Spotify, rows: list[dict]) -> list[MatchResult]:
    results = []
    for row in rows:
        query_str = " / ".join(v for v in row.values() if v)
        track = spotify_client.search_track(
            spotify,
            title=row.get("title", ""),
            artist=row.get("artist", ""),
            album=row.get("album", ""),
        )
        note = "matched" if track else "no match found — check spelling/spacing"
        results.append(MatchResult(query=query_str, matched=track, confidence_note=note))
    return results


def add_matches_to_playlist(
    spotify: spotipy.Spotify,
    playlist_name: str,
    results: list[MatchResult],
    create_if_missing: bool = True,
    dry_run: bool = False,
) -> None:
    matched_ids = [r.matched.spotify_id for r in results if r.matched]
    unmatched = [r.query for r in results if not r.matched]

    if unmatched:
        print(f"{len(unmatched)} of {len(results)} songs had no confident match:")
        for q in unmatched:
            print(f"  - {q}")

    if not matched_ids:
        print("Nothing matched — nothing to add.")
        return

    playlists = spotify_client.list_playlists(spotify)
    existing = next((p for p in playlists if p.name == playlist_name), None)

    if existing:
        spotify_client.add_tracks(spotify, existing.spotify_id, matched_ids, dry_run=dry_run)
    elif create_if_missing:
        spotify_client.create_playlist(spotify, playlist_name, matched_ids, dry_run=dry_run)
    else:
        raise ValueError(
            f"Playlist '{playlist_name}' does not exist and create_if_missing=False."
        )
