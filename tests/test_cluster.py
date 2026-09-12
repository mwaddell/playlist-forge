import numpy as np
import pytest

from playlist_forge.analyze.cluster import choose_k, cluster_kmeans
from playlist_forge.models import Track


def test_cluster_kmeans_raises_for_empty_tracks():
    with pytest.raises(ValueError, match="No usable features found"):
        cluster_kmeans([])


def test_cluster_kmeans_handles_single_track():
    tracks = [Track(spotify_id="t1", title="A", artist="X", album="", artist_genres=["rock"])]
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
            artist_genres=["rock"],
            tempo=120.0,
            energy=0.5,
            year=2000,
        ),
        Track(
            spotify_id="t2",
            title="B",
            artist="Y",
            album="",
            artist_genres=["rock"],
            tempo=120.0,
            energy=0.5,
            year=2000,
        ),
        Track(
            spotify_id="t3",
            title="C",
            artist="Z",
            album="",
            artist_genres=["rock"],
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
