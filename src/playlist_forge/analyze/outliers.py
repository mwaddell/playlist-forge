"""Per-playlist outlier detection: which tracks feel out of place.

For each playlist, builds a feature matrix of just its tracks, computes the
centroid, and scores every track by distance from that centroid. This is
deliberately playlist-scoped rather than global — a metal track is not an
"outlier" in the abstract, only relative to the specific playlist it's sitting in.
"""

from __future__ import annotations

import numpy as np

from .features import build_feature_matrix


def score_outliers(
    tracks: list,
    genre_weight: float = 1.0,
    audio_feature_weight: float = 1.0,
    year_weight: float = 0.3,
) -> list:
    """Sets `outlier_score` (higher = more out of place) on each track.
    Expects `tracks` to already be scoped to a single playlist by the caller.
    """
    if len(tracks) < 3:
        for t in tracks:
            t.outlier_score = 0.0
        return tracks

    matrix, _ = build_feature_matrix(tracks, genre_weight, audio_feature_weight, year_weight)
    if matrix.shape[1] == 0:
        for t in tracks:
            t.outlier_score = 0.0
        return tracks

    centroid = matrix.mean(axis=0)
    distances = np.linalg.norm(matrix - centroid, axis=1)
    # normalize to 0-1 so scores are comparable across playlists of different sizes
    spread = distances.max() - distances.min()
    normalized = (distances - distances.min()) / spread if spread > 0 else distances * 0

    for t, score in zip(tracks, normalized):
        t.outlier_score = float(score)
    return sorted(tracks, key=lambda t: t.outlier_score, reverse=True)


def top_outliers_by_playlist(
    tracks: list, top_n: int = 5, **feature_kwargs
) -> dict[str, list[tuple]]:
    """Groups tracks by playlist (a track can belong to several) and returns
    the top_n most-out-of-place tracks per playlist, as (track, score) pairs.

    Returns tuples rather than setting track.outlier_score in place: a track
    that appears in several playlists needs a different score per playlist,
    and Track objects are shared references across playlist groups here, so
    mutating in place would let the last-processed playlist's score clobber
    the others.
    """
    by_playlist: dict[str, list] = {}
    for t in tracks:
        for pid, pname in zip(t.playlist_ids, t.playlist_names):
            by_playlist.setdefault(pid, []).append(t)

    results: dict[str, list[tuple]] = {}
    for pid, playlist_tracks in by_playlist.items():
        scored = score_outliers(list(playlist_tracks), **feature_kwargs)
        results[pid] = [(t, t.outlier_score) for t in scored[:top_n]]
    return results
