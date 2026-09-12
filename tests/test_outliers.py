from playlist_forge.analyze.outliers import score_outliers, top_outliers_by_playlist
from playlist_forge.models import Track


def test_score_outliers_handles_empty_input():
    assert score_outliers([]) == []


def test_score_outliers_sets_zero_for_single_track():
    tracks = [Track(spotify_id="t1", title="A", artist="X", album="")]
    scored = score_outliers(tracks)
    assert len(scored) == 1
    assert scored[0].outlier_score == 0.0


def test_score_outliers_sets_zero_when_no_usable_features():
    tracks = [
        Track(spotify_id="t1", title="A", artist="X", album=""),
        Track(spotify_id="t2", title="B", artist="Y", album=""),
        Track(spotify_id="t3", title="C", artist="Z", album=""),
    ]
    scored = score_outliers(tracks)
    assert len(scored) == 3
    assert all(t.outlier_score == 0.0 for t in scored)


def test_top_outliers_by_playlist_ignores_tracks_without_playlist_metadata():
    tracks = [Track(spotify_id="t1", title="A", artist="X", album="")]
    assert top_outliers_by_playlist(tracks, top_n=3) == {}
