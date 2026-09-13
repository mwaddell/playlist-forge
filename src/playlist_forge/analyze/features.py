"""Turn Track objects into numeric feature vectors for clustering/outliers.

No API calls here — pure functions over data already pulled/enriched.
This is what makes the analyze package easy to unit test and safe to
re-run repeatedly while tuning weights.
"""

from __future__ import annotations

import numpy as np
from sklearn.preprocessing import MultiLabelBinarizer, StandardScaler

AUDIO_FEATURE_FIELDS = (
    "tempo", "energy", "danceability", "valence",
    "acousticness", "instrumentalness", "liveness",
    "loudness", "speechiness"
)


def build_feature_matrix(
    tracks: list,
    genre_weight: float = 1.0,
    audio_feature_weight: float = 1.0,
    year_weight: float = 0.3,
) -> tuple[np.ndarray, list[str]]:
    """Build a weighted numeric feature matrix from tracks.

    Args:
        tracks: Tracks to transform.
        genre_weight: Multiplier for one-hot genre features.
        audio_feature_weight: Multiplier for standardized audio features.
        year_weight: Multiplier for standardized year feature.

    Returns:
        Tuple of ``(matrix, feature_names)`` in input track order. Missing
        audio features are imputed with each column mean rather than ``0.0``
        so unmatched values do not bias vectors toward one edge.
    """
    genre_lists = [t.artist_genres or [] for t in tracks]
    mlb = MultiLabelBinarizer()
    genre_matrix = mlb.fit_transform(genre_lists).astype(float) * genre_weight
    genre_names = [f"genre:{g}" for g in mlb.classes_]

    audio_cols = []
    audio_names = []
    for field_name in AUDIO_FEATURE_FIELDS:
        col = np.array(
            [getattr(t, field_name) for t in tracks], dtype=float
        )  # NaN where None
        if np.isnan(col).all():
            continue  # nobody has this field enriched — skip rather than fabricate
        col_mean = np.nanmean(col)
        col = np.where(np.isnan(col), col_mean, col)
        audio_cols.append(col)
        audio_names.append(f"audio:{field_name}")

    if audio_cols:
        audio_matrix = np.column_stack(audio_cols)
        audio_matrix = StandardScaler().fit_transform(audio_matrix) * audio_feature_weight
    else:
        audio_matrix = np.zeros((len(tracks), 0))

    years = np.array([t.year if t.year is not None else np.nan for t in tracks], dtype=float)
    if not np.isnan(years).all():
        year_mean = np.nanmean(years)
        years = np.where(np.isnan(years), year_mean, years)
        year_col = StandardScaler().fit_transform(years.reshape(-1, 1)) * year_weight
    else:
        year_col = np.zeros((len(tracks), 0))

    parts = [p for p in (genre_matrix, audio_matrix, year_col) if p.shape[1] > 0]
    matrix = np.hstack(parts) if parts else np.zeros((len(tracks), 0))
    names = genre_names + audio_names + (["year"] if year_col.shape[1] else [])
    return matrix, names
