"""Offline checks, subsetting and statistics over a list of tracks."""

from __future__ import annotations

import math
import statistics
import unicodedata
from dataclasses import replace

from ..models import Track

AUDIO_FEATURE_FIELDS = (
    "acousticness",
    "danceability",
    "energy",
    "instrumentalness",
    "liveness",
    "loudness",
    "speechiness",
    "tempo",
    "valence",
)
NUMERIC_FIELDS = (
    "duration_ms",
    *AUDIO_FEATURE_FIELDS,
    "genre_match_confidence",
    "feature_match_confidence",
    "outlier_score",
)
OPTIONAL_FIELDS = ("isrc", "year", "duration_ms", "added_at", "genres", "genre_source", *AUDIO_FEATURE_FIELDS)


def _matches(track_id: str, track_name: str, subs: set[str]) -> bool:
    return any(s in track_id.casefold() or s in track_name.casefold() for s in subs)


def extract_playlists(tracks: list[Track], playlists: list[str] | None) -> list[Track]:
    """Keep only memberships in matching playlists (name/ID substring).

    Args:
        tracks: Input tracks.
        playlists: Playlist substrings; none means nothing is extracted.

    Returns:
        Tracks belonging to at least one matching playlist, limited to those memberships.
    """
    if not playlists:
        return []
    subs = {p.casefold() for p in playlists}
    out = []
    for t in tracks:
        keep = [(i, n) for i, n in zip(t.playlist_ids, t.playlist_names) if _matches(i, n, subs)]
        if keep:
            ids, names = zip(*keep)
            out.append(replace(t, playlist_ids=list(ids), playlist_names=list(names)))
    return out


def remove_playlists(tracks: list[Track], playlists: list[str] | None) -> list[Track]:
    """Drop memberships in matching playlists, and tracks left with no playlist.

    Args:
        tracks: Input tracks.
        playlists: Playlist substrings; none means everything is kept unchanged.

    Returns:
        Remaining tracks. Tracks without any matching membership are untouched.
    """
    if not playlists:
        return list(tracks)
    subs = {p.casefold() for p in playlists}
    out = []
    for t in tracks:
        pairs = list(zip(t.playlist_ids, t.playlist_names))
        keep = [(i, n) for i, n in pairs if not _matches(i, n, subs)]
        if len(keep) == len(pairs):
            out.append(t)
        elif keep:
            ids, names = zip(*keep)
            out.append(replace(t, playlist_ids=list(ids), playlist_names=list(names)))
    return out


def _has_special_chars(value: str) -> bool:
    return any(unicodedata.category(c) in ("Cc", "Cf", "Co", "Cs") for c in value) or value != value.strip()


def check_library(tracks: list[Track]) -> dict[str, list]:
    """Validate a library.

    Args:
        tracks: Tracks to check.

    Returns:
        Dict with ``duplicates`` (id -> tracks), ``no_playlist``, ``invalid`` (track, problems),
        ``special_chars`` (track, field names) and ``missing_optional`` (field -> count).
    """
    by_id: dict[str, list[Track]] = {}
    for t in tracks:
        by_id.setdefault(t.spotify_id, []).append(t)
    duplicates = {k: v for k, v in by_id.items() if len(v) > 1}
    no_playlist = [t for t in tracks if not t.playlist_ids and not t.playlist_names]

    invalid: list[tuple[Track, list[str]]] = []
    special: list[tuple[Track, list[str]]] = []
    for t in tracks:
        problems = [f"{f} is empty" for f in ("spotify_id", "title", "artist", "album")
                    if not isinstance(getattr(t, f), str) or not getattr(t, f).strip()]
        if len(t.playlist_ids) != len(t.playlist_names):
            problems.append("playlist_ids and playlist_names differ in length")
        if t.year is not None and not 1000 <= t.year <= 9999:
            problems.append(f"year {t.year} is not a valid year")
        if t.duration_ms is not None and t.duration_ms < 0:
            problems.append("duration_ms is negative")
        for f in NUMERIC_FIELDS:
            v = getattr(t, f)
            if isinstance(v, float) and not math.isfinite(v):
                problems.append(f"{f} is not finite")
        if problems:
            invalid.append((t, problems))
        bad = [f for f in ("spotify_id", "title", "artist", "album")
               if isinstance(getattr(t, f), str) and _has_special_chars(getattr(t, f))]
        bad += [f"playlist_names[{i}]" for i, n in enumerate(t.playlist_names) if _has_special_chars(n)]
        if bad:
            special.append((t, bad))

    missing = {}
    for f in OPTIONAL_FIELDS:
        n = sum(1 for t in tracks if getattr(t, f) in (None, "", []))
        if n:
            missing[f] = n
    return {
        "duplicates": duplicates,
        "no_playlist": no_playlist,
        "invalid": invalid,
        "special_chars": special,
        "missing_optional": missing,
    }


def is_fully_enriched(track: Track) -> bool:
    """Whether a track has genres and all audio features."""
    return bool(track.genres) and all(getattr(track, f) is not None for f in AUDIO_FEATURE_FIELDS)


def _summary(values: list[float]) -> dict[str, float] | None:
    if not values:
        return None
    return {
        "count": len(values),
        "min": min(values),
        "max": max(values),
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
    }


def compute_stats(tracks: list[Track]) -> dict:
    """Compute basic library statistics.

    Args:
        tracks: Tracks to summarize.

    Returns:
        Dict of counts, sorted genres, year summary and per-field numeric summaries.
    """
    playlists = {i for t in tracks for i in t.playlist_ids}
    genres = sorted({g for t in tracks for g in t.genres}, key=str.casefold)
    numeric = {}
    for f in NUMERIC_FIELDS:
        s = _summary([getattr(t, f) for t in tracks if getattr(t, f) is not None
                      and not (isinstance(getattr(t, f), float) and math.isnan(getattr(t, f)))])
        if s:
            numeric[f] = s
    return {
        "tracks": len(tracks),
        "playlists": len(playlists),
        "artists": len({t.artist for t in tracks}),
        "fully_enriched": sum(1 for t in tracks if is_fully_enriched(t)),
        "genres": genres,
        "years": _summary([t.year for t in tracks if t.year is not None]),
        "numeric": numeric,
    }
