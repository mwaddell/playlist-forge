"""Cluster tracks by genre + audio-feature + year similarity.

Two algorithms on purpose:
  - KMeans: fast, forces every track into a cluster, good for "split this
    mega-playlist into N sub-genres."
  - HDBSCAN (optional dependency): finds clusters of varying density and
    explicitly labels sparse points as noise (-1) — better suited to
    "which songs don't belong anywhere" than forcing a k-means assignment.
"""

from __future__ import annotations

import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

from .features import build_feature_matrix


def choose_k(matrix: np.ndarray, k_min: int = 2, k_max: int = 12) -> int:
    """Select a KMeans cluster count using silhouette score.

    Args:
        matrix: Feature matrix where each row is a track.
        k_min: Minimum candidate cluster count.
        k_max: Maximum candidate cluster count.

    Returns:
        Selected cluster count.
    """
    n = matrix.shape[0]
    k_max = min(k_max, n - 1)
    if k_max < k_min:
        return max(1, n)

    best_k, best_score = k_min, -1.0
    for k in range(k_min, k_max + 1):
        labels = KMeans(n_clusters=k, n_init="auto", random_state=42).fit_predict(matrix)
        if len(set(labels)) < 2:
            continue
        score = silhouette_score(matrix, labels)
        if score > best_score:
            best_k, best_score = k, score
    return best_k


def cluster_kmeans(
    tracks: list,
    k: int | str = "auto",
    genre_weight: float = 1.0,
    audio_feature_weight: float = 1.0,
    audio_feature_weights: dict[str, float] | None = None,
    year_weight: float = 0.3,
) -> list:
    """Assign ``cluster_id`` values using KMeans.

    Args:
        tracks: Tracks to cluster in place.
        k: Cluster count or ``"auto"`` for silhouette-based selection.
        genre_weight: Multiplier for one-hot genre features.
        audio_feature_weight: Default multiplier for scaled audio features.
        audio_feature_weights: Optional per-feature multipliers keyed by audio
            field name.
        year_weight: Multiplier for standardized year feature.

    Returns:
        The input tracks with ``cluster_id`` populated.
    """
    matrix, _ = build_feature_matrix(
        tracks,
        genre_weight=genre_weight,
        audio_feature_weight=audio_feature_weight,
        audio_feature_weights=audio_feature_weights,
        year_weight=year_weight,
    )
    if matrix.shape[1] == 0:
        raise ValueError(
            "No usable features found (no genres and no enriched audio features). "
            "Run `playlist-forge enrich` first, or check that artist genres were pulled."
        )

    k_int = choose_k(matrix) if k == "auto" else int(k)
    k_int = max(1, min(k_int, matrix.shape[0]))
    labels = KMeans(n_clusters=k_int, n_init="auto", random_state=42).fit_predict(matrix)

    for track, label in zip(tracks, labels):
        track.cluster_id = int(label)
    return tracks


def cluster_hdbscan(
    tracks: list,
    genre_weight: float = 1.0,
    audio_feature_weight: float = 1.0,
    audio_feature_weights: dict[str, float] | None = None,
    year_weight: float = 0.3,
    min_cluster_size: int = 5,
) -> list:
    """Assign ``cluster_id`` values using HDBSCAN.

    Args:
        tracks: Tracks to cluster in place.
        genre_weight: Multiplier for one-hot genre features.
        audio_feature_weight: Default multiplier for scaled audio features.
        audio_feature_weights: Optional per-feature multipliers keyed by audio
            field name.
        year_weight: Multiplier for standardized year feature.
        min_cluster_size: Minimum cluster size parameter for HDBSCAN.

    Returns:
        The input tracks with ``cluster_id`` populated.
    """
    try:
        import hdbscan
    except ImportError as exc:
        raise ImportError(
            "HDBSCAN clustering requires the optional dependency: "
            "use `poetry install --extras hdbscan` from a cloned repo, "
            "or `pip install 'playlist-forge[hdbscan]'` for an installed package"
        ) from exc

    matrix, _ = build_feature_matrix(
        tracks,
        genre_weight=genre_weight,
        audio_feature_weight=audio_feature_weight,
        audio_feature_weights=audio_feature_weights,
        year_weight=year_weight,
    )
    if matrix.shape[1] == 0:
        raise ValueError("No usable features found — run `playlist-forge enrich` first.")

    clusterer = hdbscan.HDBSCAN(min_cluster_size=min_cluster_size)
    labels = clusterer.fit_predict(matrix)  # -1 == noise / doesn't belong anywhere
    for track, label in zip(tracks, labels):
        track.cluster_id = int(label)
    return tracks
