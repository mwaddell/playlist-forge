import numpy as np

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
