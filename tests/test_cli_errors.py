from __future__ import annotations

from pathlib import Path

import pytest
import typer

from playlist_forge import cli
from playlist_forge.errors import AuthFailureError
from playlist_forge.io_formats import read_tracks, write_tracks
from playlist_forge.models import Track


class DummySettings:
    config = {}


def test_pull_exits_cleanly_for_expected_api_errors(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(cli, "load_settings", lambda: DummySettings())

    def raise_auth(_settings):
        raise AuthFailureError("Spotify authentication failed (401).")

    monkeypatch.setattr(cli.auth, "get_spotify_client", raise_auth)

    with pytest.raises(typer.Exit) as exc_info:
        cli.pull(output=Path(tmp_path / "out.json"), fmt=None, playlist=None)

    assert exc_info.value.exit_code == 1
    captured = capsys.readouterr()
    assert "Error: Spotify authentication failed (401)." in captured.err


def test_analyze_cluster_rejects_unknown_algorithm(capsys, tmp_path):
    with pytest.raises(typer.Exit) as exc_info:
        cli.analyze_cluster(
            input=Path(tmp_path / "in.json"),
            output=Path(tmp_path / "out.json"),
            fmt=None,
            algorithm="not-a-real-algorithm",
            k="auto",
            genre_weight=1.0,
            audio_feature_weight=1.0,
            year_weight=0.3,
        )

    assert exc_info.value.exit_code == 1
    captured = capsys.readouterr()
    assert "Unsupported --algorithm 'not-a-real-algorithm'" in captured.err


def test_playlist_name_for_id_uses_matching_playlist_index():
    t = Track(
        spotify_id="t1",
        title="A",
        artist="X",
        album="",
        playlist_ids=["p-other", "p-target"],
        playlist_names=["Other", "Target"],
    )
    assert cli._playlist_name_for_id(t, "p-target") == "Target"


def test_analyze_cluster_uses_config_defaults_for_audio_weights(monkeypatch, tmp_path):
    class ConfiguredSettings:
        config = {
            "cluster": {
                "genre_weight": 1.5,
                "audio_feature_weight": 2.0,
                "audio_tempo_weight": 0.4,
                "year_weight": 0.7,
            }
        }

    monkeypatch.setattr(cli, "load_settings", lambda: ConfiguredSettings())
    monkeypatch.setattr(cli.io_formats, "read_tracks", lambda _path: [])
    monkeypatch.setattr(cli.io_formats, "write_tracks", lambda *_args, **_kwargs: None)
    captured_kwargs: dict = {}

    def fake_cluster_kmeans(_tracks, **kwargs):
        captured_kwargs.update(kwargs)
        return []

    monkeypatch.setattr(cli.cluster_mod, "cluster_kmeans", fake_cluster_kmeans)

    cli.analyze_cluster(
        input=Path(tmp_path / "in.json"),
        output=Path(tmp_path / "out.json"),
        fmt=None,
        algorithm="kmeans",
        k="auto",
    )

    assert captured_kwargs["genre_weight"] == 1.5
    assert captured_kwargs["audio_feature_weight"] == 2.0
    assert captured_kwargs["year_weight"] == 0.7
    assert captured_kwargs["audio_feature_weights"] == {"tempo": 0.4}


def test_analyze_cluster_cli_audio_weight_overrides_config(monkeypatch, tmp_path):
    class ConfiguredSettings:
        config = {"cluster": {"audio_feature_weight": 2.0, "audio_tempo_weight": 0.4}}

    monkeypatch.setattr(cli, "load_settings", lambda: ConfiguredSettings())
    monkeypatch.setattr(cli.io_formats, "read_tracks", lambda _path: [])
    monkeypatch.setattr(cli.io_formats, "write_tracks", lambda *_args, **_kwargs: None)
    captured_kwargs: dict = {}

    def fake_cluster_kmeans(_tracks, **kwargs):
        captured_kwargs.update(kwargs)
        return []

    monkeypatch.setattr(cli.cluster_mod, "cluster_kmeans", fake_cluster_kmeans)

    cli.analyze_cluster(
        input=Path(tmp_path / "in.json"),
        output=Path(tmp_path / "out.json"),
        fmt=None,
        algorithm="kmeans",
        k="auto",
        audio_feature_weight=3.0,
        audio_tempo_weight=0.9,
        audio_valence_weight=1.2,
    )

    assert captured_kwargs["audio_feature_weight"] == 3.0
    assert captured_kwargs["audio_feature_weights"] == {"tempo": 0.9, "valence": 1.2}


def test_convert_uses_inferred_formats(monkeypatch, tmp_path):
    tracks = [Track(spotify_id="abc", title="Song", artist="Artist", album="Album")]
    captured_args: dict = {}

    def fake_read(path):
        captured_args["read_path"] = path
        return tracks

    def fake_write(written_tracks, path, fmt):
        captured_args["written_tracks"] = written_tracks
        captured_args["write_path"] = path
        captured_args["fmt"] = fmt

    monkeypatch.setattr(cli.io_formats, "read_tracks", fake_read)
    monkeypatch.setattr(cli.io_formats, "write_tracks", fake_write)

    input_path = Path(tmp_path / "library.json")
    output_path = Path(tmp_path / "library.tsv")
    cli.library_convert(input=input_path, output=output_path, fmt=None)

    assert captured_args["read_path"] == input_path
    assert captured_args["written_tracks"] == tracks
    assert captured_args["write_path"] == output_path
    assert captured_args["fmt"] is None


def test_convert_with_explicit_output_format(tmp_path):
    input_path = Path(tmp_path / "library.json")
    output_path = Path(tmp_path / "library_copy.json")
    tracks = [Track(spotify_id="abc", title="Song", artist="Artist", album="Album")]
    write_tracks(tracks, input_path)

    cli.library_convert(input=input_path, output=output_path, fmt="tsv")
    output_rows = output_path.read_text(encoding="utf-8").splitlines()

    assert output_rows[0].startswith("spotify_id\ttitle\tartist\talbum\t")
    loaded = read_tracks(output_path, fmt="tsv")
    assert loaded[0].spotify_id == "abc"


def test_convert_same_format_creates_copy(tmp_path):
    input_path = Path(tmp_path / "library.json")
    output_path = Path(tmp_path / "library_copy.json")
    tracks = [Track(spotify_id="abc", title="Song", artist="Artist", album="Album")]
    write_tracks(tracks, input_path)

    cli.library_convert(input=input_path, output=output_path, fmt=None)

    copied = read_tracks(output_path)
    assert [t.spotify_id for t in copied] == ["abc"]
