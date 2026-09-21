import pytest

from playlist_forge.analyze.outliers import score_outliers, top_outliers_by_playlist
from playlist_forge.cli import _filter_tracks_by_playlist
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


def test_top_outliers_by_playlist_does_not_clobber_shared_track_state():
    shared = Track(
        spotify_id="shared",
        title="Shared",
        artist="X",
        album="",
        playlist_ids=["p1", "p2"],
        playlist_names=["One", "Two"],
        genres=["rock"],
        tempo=120.0,
        year=2000,
    )
    p1_other = Track(
        spotify_id="p1-other",
        title="P1",
        artist="A",
        album="",
        playlist_ids=["p1"],
        playlist_names=["One"],
        genres=["rock"],
        tempo=121.0,
        year=2001,
    )
    p2_other = Track(
        spotify_id="p2-other",
        title="P2",
        artist="B",
        album="",
        playlist_ids=["p2"],
        playlist_names=["Two"],
        genres=["jazz"],
        tempo=90.0,
        year=1990,
    )

    results = top_outliers_by_playlist([shared, p1_other, p2_other], top_n=2)

    assert shared.outlier_score is None
    assert len(results["p1"]) == 2
    assert len(results["p2"]) == 2


def test_filtered_tracks_do_not_produce_outliers_for_unselected_playlists():
    shared = Track(
        spotify_id="shared",
        title="Shared",
        artist="X",
        album="",
        playlist_ids=["selected", "other"],
        playlist_names=["Selected", "Other"],
    )
    selected = Track(
        spotify_id="selected-only",
        title="Selected",
        artist="X",
        album="",
        playlist_ids=["selected"],
        playlist_names=["Selected"],
    )

    results = top_outliers_by_playlist(
        _filter_tracks_by_playlist([shared, selected], ["selected"])
    )

    assert set(results) == {"selected"}


def test_top_outliers_by_playlist_raises_on_mismatched_playlist_metadata():
    tracks = [
        Track(
            spotify_id="t1",
            title="A",
            artist="X",
            album="",
            playlist_ids=["p1", "p2"],
            playlist_names=["One"],
        )
    ]
    with pytest.raises(ValueError) as exc_info:
        top_outliers_by_playlist(tracks)

    assert "mismatched playlist metadata" in str(exc_info.value)
