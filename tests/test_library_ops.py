from __future__ import annotations

from typer.testing import CliRunner

from playlist_forge import cli
from playlist_forge.io_formats import read_tracks, write_tracks
from playlist_forge.library.ops import check_library, compute_stats, extract_playlists, remove_playlists
from playlist_forge.models import Track

runner = CliRunner()


def _tracks():
    return [
        Track("1", "A", "X", "Al", ["p1", "p2"], ["Rock", "Pop"], year=2000, tempo=100.0),
        Track("2", "B", "Y", "Al", ["p2"], ["Pop"], year=2010),
        Track("2", "B", "Y", "Al", ["p3"], ["Jazz"]),
        Track("3", "C\x00", "Y", "Al"),
    ]


def test_extract_and_remove():
    ts = _tracks()
    assert extract_playlists(ts, None) == []
    got = extract_playlists(ts, ["rock"])
    assert [t.spotify_id for t in got] == ["1"] and got[0].playlist_names == ["Rock"]
    assert remove_playlists(ts, None) == ts
    rest = remove_playlists(ts, ["pop"])
    assert [t.playlist_names for t in rest] == [["Rock"], ["Jazz"], []]


def test_check_and_stats():
    res = check_library(_tracks())
    assert list(res["duplicates"]) == ["2"]
    assert [t.spotify_id for t in res["no_playlist"]] == ["3"]
    assert res["special_chars"][0][0].spotify_id == "3"
    s = compute_stats(_tracks())
    assert s["tracks"] == 4 and s["playlists"] == 3 and s["artists"] == 2
    assert s["years"]["median"] == 2005 and s["numeric"]["tempo"]["max"] == 100.0


def test_cli_commands(tmp_path):
    src = tmp_path / "in.json"
    write_tracks(_tracks(), src)
    out = tmp_path / "out.json"
    r = runner.invoke(cli.app, ["library", "check", "-i", str(src)])
    assert r.exit_code == 0 and "duplicate" in r.output and "no playlist" in r.output
    r = runner.invoke(cli.app, ["library", "extract", "-i", str(src), "-o", str(out)])
    assert r.exit_code == 0 and read_tracks(out) == []
    r = runner.invoke(cli.app, ["library", "remove", "-i", str(src), "-o", str(out), "--playlist", "Pop"])
    assert r.exit_code == 0 and len(read_tracks(out)) == 3
    r = runner.invoke(cli.app, ["library", "stats", "-i", str(src), "--playlist", "Pop"])
    assert r.exit_code == 0 and "Tracks: 2" in r.output
