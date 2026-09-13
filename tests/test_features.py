import numpy as np
import pytest

from playlist_forge.analyze.features import build_feature_matrix
from playlist_forge.models import Track


def test_feature_matrix_shape_with_genres_only():
    tracks = [
        Track(spotify_id="a", title="A", artist="X", album="", artist_genres=["rock"]),
        Track(spotify_id="b", title="B", artist="Y", album="", artist_genres=["pop"]),
    ]
    matrix, names = build_feature_matrix(tracks)
    assert matrix.shape[0] == 2
    assert any(n.startswith("genre:") for n in names)
    assert not any(n.startswith("audio:") for n in names)  # no enrichment present


def test_feature_matrix_includes_audio_features_when_present():
    tracks = [
        Track(spotify_id="a", title="A", artist="X", album="", tempo=120.0, energy=0.8),
        Track(spotify_id="b", title="B", artist="Y", album="", tempo=90.0, energy=0.2),
    ]
    _matrix, names = build_feature_matrix(tracks)
    assert any(n.startswith("audio:") for n in names)


def test_feature_matrix_handles_partial_audio_features_without_crashing():
    tracks = [
        Track(spotify_id="a", title="A", artist="X", album="", tempo=120.0),
        Track(spotify_id="b", title="B", artist="Y", album="", tempo=None),
    ]
    matrix, _names = build_feature_matrix(tracks)
    assert matrix.shape[0] == 2
    assert not np.isnan(matrix).any()  # no NaNs leaked into output


def test_feature_matrix_scales_tempo_and_loudness_to_zero_one():
    tracks = [
        Track(spotify_id="a", title="A", artist="X", album="", tempo=250.0, loudness=0.0),
        Track(spotify_id="b", title="B", artist="Y", album="", tempo=0.0, loudness=-60.0),
    ]

    matrix, names = build_feature_matrix(tracks)
    tempo_idx = names.index("audio:tempo")
    loudness_idx = names.index("audio:loudness")

    assert matrix[0, tempo_idx] == 1.0
    assert matrix[1, tempo_idx] == 0.0
    assert matrix[0, loudness_idx] == 1.0
    assert matrix[1, loudness_idx] == 0.0


def test_feature_matrix_applies_per_feature_audio_weight_overrides():
    tracks = [
        Track(spotify_id="a", title="A", artist="X", album="", valence=0.2, tempo=100.0),
        Track(spotify_id="b", title="B", artist="Y", album="", valence=0.8, tempo=200.0),
    ]

    matrix, names = build_feature_matrix(
        tracks,
        audio_feature_weight=2.0,
        audio_feature_weights={"tempo": 0.5},
    )
    tempo_idx = names.index("audio:tempo")
    valence_idx = names.index("audio:valence")

    assert matrix[0, tempo_idx] == pytest.approx(0.2)  # (100/250) * 0.5
    assert matrix[1, tempo_idx] == pytest.approx(0.4)  # (200/250) * 0.5
    assert matrix[0, valence_idx] == pytest.approx(0.4)  # 0.2 * default 2.0
    assert matrix[1, valence_idx] == pytest.approx(1.6)  # 0.8 * default 2.0
