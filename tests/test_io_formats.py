from playlist_forge.io_formats import infer_format, read_tracks, write_tracks
from playlist_forge.models import Track


def sample_tracks():
    return [
        Track(
            spotify_id="abc123",
            title="Everything In Its Right Place",
            artist="Radiohead",
            album="Kid A",
            playlist_ids=["p1", "p2"],
            playlist_names=["Chill", "Focus"],
            isrc="GBUM71029601",
            year=2000,
            duration_ms=249000,
            genres=["art rock", "alternative rock"],
            genre_source="getgenre",
            genre_match_confidence=0.95,
            tempo=122.5,
            energy=0.45,
        ),
        Track(
            spotify_id="def456",
            title="Idioteque",
            artist="Radiohead",
            album="Kid A",
            playlist_ids=["p1"],
            playlist_names=["Chill"],
        ),
    ]


def test_infer_format():
    assert infer_format("out.json") == "json"
    assert infer_format("out.csv") == "csv"
    assert infer_format("out.tsv") == "tsv"
    assert infer_format("out.txt") == "tsv"
    assert infer_format("out.xyz") == "csv"  # default fallback
    assert infer_format("txt") == "csv"  # default fallback


def test_json_round_trip(tmp_path):
    path = tmp_path / "tracks.json"
    tracks = sample_tracks()
    write_tracks(tracks, path)
    loaded = read_tracks(path)

    assert len(loaded) == 2
    assert loaded[0].spotify_id == "abc123"
    assert loaded[0].playlist_ids == ["p1", "p2"]
    assert loaded[0].genres == ["art rock", "alternative rock"]
    assert loaded[0].genre_source == "getgenre"
    assert loaded[0].genre_match_confidence == 0.95
    assert loaded[0].tempo == 122.5
    assert loaded[1].tempo is None


def test_csv_round_trip(tmp_path):
    path = tmp_path / "tracks.csv"
    tracks = sample_tracks()
    write_tracks(tracks, path)
    loaded = read_tracks(path)

    assert len(loaded) == 2
    assert loaded[0].playlist_ids == ["p1", "p2"]
    assert loaded[0].year == 2000
    assert loaded[0].genres == ["art rock", "alternative rock"]
    assert loaded[0].tempo == 122.5
    assert loaded[1].year is None


def test_tsv_round_trip(tmp_path):
    path = tmp_path / "tracks.tsv"
    tracks = sample_tracks()
    write_tracks(tracks, path)
    loaded = read_tracks(path)

    assert len(loaded) == 2
    assert loaded[0].title == "Everything In Its Right Place"
    assert loaded[0].genres == ["art rock", "alternative rock"]


def test_json_reads_legacy_artist_genres_field(tmp_path):
    path = tmp_path / "legacy_tracks.json"
    path.write_text(
        """
[
  {
    "spotify_id": "abc123",
    "title": "Everything In Its Right Place",
    "artist": "Radiohead",
    "album": "Kid A",
    "artist_genres": ["art rock", "alternative rock"]
  }
]
""".strip(),
        encoding="utf-8",
    )

    loaded = read_tracks(path)

    assert loaded[0].genres == ["art rock", "alternative rock"]
