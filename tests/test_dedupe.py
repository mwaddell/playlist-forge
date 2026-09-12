from playlist_forge.analyze.dedupe import find_duplicate_tracks, find_playlist_overlaps
from playlist_forge.models import Track


def test_duplicate_detection_handles_empty_input():
    assert find_duplicate_tracks([]) == []


def test_duplicate_detection_skips_same_spotify_id():
    tracks = [
        Track(spotify_id="same", title="Song", artist="Band", album="X", isrc="US1234567890"),
        Track(spotify_id="same", title="Song (Live)", artist="Band", album="Y", isrc="US1234567890"),
    ]
    assert find_duplicate_tracks(tracks, threshold=0.0) == []


def test_finds_duplicate_by_isrc():
    tracks = [
        Track(spotify_id="a1", title="Song (Remaster)", artist="Band", album="X",
              isrc="US1234567890"),
        Track(spotify_id="a2", title="Song", artist="Band", album="Y",
              isrc="US1234567890"),
    ]
    dups = find_duplicate_tracks(tracks, threshold=0.9)
    assert len(dups) == 1
    assert dups[0].similarity == 1.0


def test_finds_duplicate_by_fuzzy_title():
    tracks = [
        Track(spotify_id="a1", title="Idioteque", artist="Radiohead", album="Kid A"),
        Track(spotify_id="a2", title="Idioteque - Live", artist="Radiohead",
              album="I Might Be Wrong"),
        Track(spotify_id="a3", title="Completely Unrelated Song", artist="Someone Else", album="Z"),
    ]
    dups = find_duplicate_tracks(tracks, threshold=0.6)
    matched_ids = {(d.track_a_id, d.track_b_id) for d in dups}
    assert ("a1", "a2") in matched_ids
    assert not any("a3" in pair for pair in matched_ids)


def test_playlist_overlap_detection():
    tracks = [
        Track(spotify_id="t1", title="A", artist="X", album="",
              playlist_ids=["p1", "p2"], playlist_names=["Chill", "Study"]),
        Track(spotify_id="t2", title="B", artist="X", album="",
              playlist_ids=["p1", "p2"], playlist_names=["Chill", "Study"]),
        Track(spotify_id="t3", title="C", artist="X", album="",
              playlist_ids=["p1"], playlist_names=["Chill"]),
        Track(spotify_id="t4", title="D", artist="X", album="",
              playlist_ids=["p3"], playlist_names=["Metal"]),
    ]
    overlaps = find_playlist_overlaps(tracks, threshold=0.5)
    pairs = {(o.playlist_a_id, o.playlist_b_id) for o in overlaps}
    assert ("p1", "p2") in pairs
    assert not any("p3" in pair for pair in pairs)


def test_playlist_overlap_handles_empty_input():
    assert find_playlist_overlaps([]) == []


def test_playlist_overlap_with_single_playlist_returns_no_pairs():
    tracks = [
        Track(
            spotify_id="t1",
            title="A",
            artist="X",
            album="",
            playlist_ids=["p1"],
            playlist_names=["Only Playlist"],
        ),
        Track(
            spotify_id="t2",
            title="B",
            artist="Y",
            album="",
            playlist_ids=["p1"],
            playlist_names=["Only Playlist"],
        ),
    ]
    assert find_playlist_overlaps(tracks, threshold=0.0) == []
