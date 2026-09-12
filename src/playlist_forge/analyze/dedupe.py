"""Two kinds of duplication this tool cares about:

1. Near-duplicate tracks: the same song appearing under different Spotify
   IDs (remaster, live version, deluxe edition) — fuzzy title+artist match.
2. Near-duplicate playlists: two playlists that share enough tracks that
   they're candidates for merging.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

from rapidfuzz import fuzz


@dataclass
class DuplicateTrackPair:
    track_a_id: str
    track_b_id: str
    title_a: str
    title_b: str
    artist_a: str
    artist_b: str
    similarity: float


@dataclass
class PlaylistOverlap:
    playlist_a_id: str
    playlist_b_id: str
    playlist_a_name: str
    playlist_b_name: str
    shared_track_count: int
    jaccard_similarity: float


def _norm(s: str) -> str:
    return " ".join(s.lower().split())


def find_duplicate_tracks(tracks: list, threshold: float = 0.90) -> list[DuplicateTrackPair]:
    """Find likely duplicate songs across different Spotify track IDs.

    Args:
        tracks: Tracks to compare pairwise.
        threshold: Minimum weighted similarity score to include.

    Returns:
        Duplicate track pairs sorted by descending similarity. This
        implementation is ``O(n^2)`` and intended for modest library sizes.
    """
    pairs = []
    for a, b in combinations(tracks, 2):
        if a.spotify_id == b.spotify_id:
            continue
        # cheap pre-filter: same ISRC is an automatic match, skip fuzzy scoring
        if a.isrc and b.isrc and a.isrc == b.isrc:
            pairs.append(
                DuplicateTrackPair(a.spotify_id, b.spotify_id, a.title, b.title,
                                    a.artist, b.artist, similarity=1.0)
            )
            continue
        title_sim = fuzz.token_sort_ratio(_norm(a.title), _norm(b.title)) / 100
        artist_sim = fuzz.token_sort_ratio(_norm(a.artist), _norm(b.artist)) / 100
        combined = (title_sim * 0.7) + (artist_sim * 0.3)
        if combined >= threshold:
            pairs.append(
                DuplicateTrackPair(a.spotify_id, b.spotify_id, a.title, b.title,
                                    a.artist, b.artist, similarity=round(combined, 3))
            )
    return sorted(pairs, key=lambda p: p.similarity, reverse=True)


def find_playlist_overlaps(
    tracks: list, threshold: float = 0.60
) -> list[PlaylistOverlap]:
    """Find playlist pairs with high track overlap.

    Args:
        tracks: Tracks containing playlist membership fields.
        threshold: Minimum Jaccard similarity to include.

    Returns:
        Playlist overlap records sorted by descending similarity.
    """
    playlist_track_ids: dict[str, set[str]] = {}
    playlist_names: dict[str, str] = {}
    for t in tracks:
        for pid, pname in zip(t.playlist_ids, t.playlist_names):
            playlist_track_ids.setdefault(pid, set()).add(t.spotify_id)
            playlist_names[pid] = pname

    overlaps = []
    for (pid_a, ids_a), (pid_b, ids_b) in combinations(playlist_track_ids.items(), 2):
        if not ids_a or not ids_b:
            continue
        shared = ids_a & ids_b
        union = ids_a | ids_b
        jaccard = len(shared) / len(union) if union else 0.0
        if jaccard >= threshold and shared:
            overlaps.append(
                PlaylistOverlap(
                    playlist_a_id=pid_a,
                    playlist_b_id=pid_b,
                    playlist_a_name=playlist_names[pid_a],
                    playlist_b_name=playlist_names[pid_b],
                    shared_track_count=len(shared),
                    jaccard_similarity=round(jaccard, 3),
                )
            )
    return sorted(overlaps, key=lambda o: o.jaccard_similarity, reverse=True)
