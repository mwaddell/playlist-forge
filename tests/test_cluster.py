import sys

import numpy as np
import pytest

from playlist_forge.analyze import cluster as cluster_mod
from playlist_forge.analyze.cluster import choose_k, cluster_hdbscan, cluster_kmeans
from playlist_forge.models import Track


def test_cluster_kmeans_raises_for_empty_tracks():
    with pytest.raises(ValueError, match="No usable features found"):
        cluster_kmeans([])


def test_cluster_kmeans_handles_single_track():
    tracks = [Track(spotify_id="t1", title="A", artist="X", album="", genres=["rock"])]
    clustered = cluster_kmeans(tracks, k="auto")
    assert len(clustered) == 1
    assert clustered[0].cluster_id == 0


def test_cluster_kmeans_handles_all_identical_vectors():
    tracks = [
        Track(
            spotify_id="t1",
            title="A",
            artist="X",
            album="",
            genres=["rock"],
            tempo=120.0,
            energy=0.5,
            year=2000,
        ),
        Track(
            spotify_id="t2",
            title="B",
            artist="Y",
            album="",
            genres=["rock"],
            tempo=120.0,
            energy=0.5,
            year=2000,
        ),
        Track(
            spotify_id="t3",
            title="C",
            artist="Z",
            album="",
            genres=["rock"],
            tempo=120.0,
            energy=0.5,
            year=2000,
        ),
    ]
    clustered = cluster_kmeans(tracks, k="auto")
    assert len(clustered) == 3
    assert all(t.cluster_id is not None for t in clustered)


def test_choose_k_returns_one_for_single_row_matrix():
    matrix = np.array([[1.0, 2.0]])
    assert choose_k(matrix) == 1


def test_cluster_kmeans_passes_audio_feature_weight_overrides(monkeypatch):
    tracks = [
        Track(spotify_id="t1", title="A", artist="X", album="", genres=["rock"]),
        Track(spotify_id="t2", title="B", artist="Y", album="", genres=["pop"]),
    ]
    captured_kwargs: dict = {}

    def fake_build_feature_matrix(_tracks, **kwargs):
        captured_kwargs.update(kwargs)
        return np.array([[0.0], [1.0]]), ["audio:tempo"]

    monkeypatch.setattr(cluster_mod, "build_feature_matrix", fake_build_feature_matrix)

    cluster_kmeans(
        tracks,
        k=2,
        audio_feature_weight=1.5,
        audio_feature_weights={"tempo": 0.7},
    )

    assert captured_kwargs["audio_feature_weight"] == 1.5
    assert captured_kwargs["audio_feature_weights"] == {"tempo": 0.7}


def test_cluster_hdbscan_passes_audio_feature_weight_overrides(monkeypatch):
    tracks = [
        Track(spotify_id="t1", title="A", artist="X", album="", genres=["rock"]),
        Track(spotify_id="t2", title="B", artist="Y", album="", genres=["pop"]),
    ]
    captured_kwargs: dict = {}

    def fake_build_feature_matrix(_tracks, **kwargs):
        captured_kwargs.update(kwargs)
        return np.array([[0.0], [1.0]]), ["audio:tempo"]

    class FakeHDBSCAN:
        def __init__(self, min_cluster_size):
            self.min_cluster_size = min_cluster_size

        def fit_predict(self, _matrix):
            return np.array([0, 1])

    monkeypatch.setattr(cluster_mod, "build_feature_matrix", fake_build_feature_matrix)
    fake_module = type("FakeHDBSCANModule", (), {"HDBSCAN": FakeHDBSCAN})
    monkeypatch.setitem(sys.modules, "hdbscan", fake_module)

    cluster_hdbscan(
        tracks,
        min_cluster_size=2,
        audio_feature_weight=1.5,
        audio_feature_weights={"tempo": 0.7},
    )

    assert captured_kwargs["audio_feature_weight"] == 1.5
    assert captured_kwargs["audio_feature_weights"] == {"tempo": 0.7}
