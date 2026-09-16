from __future__ import annotations

from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from playlist_forge import cli
from playlist_forge.errors import AuthFailureError
from playlist_forge.io_formats import read_tracks, write_tracks
from playlist_forge.models import Track

runner = CliRunner()


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


def test_auth_logout_reports_when_token_removed(monkeypatch, capsys):
    monkeypatch.setattr(cli.auth, "logout", lambda: True)
    monkeypatch.setattr(cli.auth, "TOKEN_PATH", Path("/tmp/token.json"))

    cli.auth_logout()

    captured = capsys.readouterr()
    assert "Logged out. Removed cached token at /tmp/token.json." in captured.out


def test_auth_logout_reports_when_token_missing(monkeypatch, capsys):
    monkeypatch.setattr(cli.auth, "logout", lambda: False)
    monkeypatch.setattr(cli.auth, "TOKEN_PATH", Path("/tmp/token.json"))

    cli.auth_logout()

    captured = capsys.readouterr()
    assert "No cached token found at /tmp/token.json." in captured.out


def test_config_init_reports_written_path(monkeypatch, capsys):
    monkeypatch.setattr(cli, "initialize_config", lambda force=False: Path("/tmp/config.json"))

    cli.config_init()

    captured = capsys.readouterr()
    assert "Wrote default configuration to /tmp/config.json." in captured.out


def test_config_init_passes_force_flag(monkeypatch):
    captured_args: dict = {}

    def fake_initialize_config(force=False) -> Path:
        captured_args["force"] = force
        return Path("/tmp/config.json")

    monkeypatch.setattr(cli, "initialize_config", fake_initialize_config)

    cli.config_init(force=True)

    assert captured_args["force"] is True


def test_config_clientid_reports_written_path(monkeypatch, capsys):
    captured_args: dict = {}

    def fake_set_spotify_client_id(client_id: str) -> Path:
        captured_args["client_id"] = client_id
        return Path("/tmp/config.json")

    monkeypatch.setattr(cli, "set_spotify_client_id", fake_set_spotify_client_id)

    cli.config_clientid("spotify-client-id")

    captured = capsys.readouterr()
    assert captured_args["client_id"] == "spotify-client-id"
    assert "Updated Spotify client ID in /tmp/config.json." in captured.out


def test_config_getgenres_reports_written_path(monkeypatch, capsys):
    captured_args: dict = {}

    def fake_set_getgenre_credentials(username: str, password: str) -> Path:
        captured_args["username"] = username
        captured_args["password"] = password
        return Path("/tmp/config.json")

    monkeypatch.setattr(cli, "set_getgenre_credentials", fake_set_getgenre_credentials)
    monkeypatch.setattr(cli.typer, "prompt", lambda *_args, **_kwargs: "genre-pass")

    cli.config_getgenres("genre-user")

    captured = capsys.readouterr()
    assert captured_args == {"username": "genre-user", "password": "genre-pass"}
    assert "Updated GetGenre credentials in /tmp/config.json." in captured.out


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


def test_enrich_uses_reccobeats_by_default(monkeypatch, capsys, tmp_path):
    tracks = [Track(spotify_id="abc", title="Song", artist="Artist", album="Album")]
    captured: dict = {}

    class FakeClient:
        def __init__(self, _settings):
            captured["client"] = "reccobeats"

        def enrich(self, input_tracks):
            input_tracks[0].feature_source = "reccobeats"
            return input_tracks

    monkeypatch.setattr(cli, "load_settings", lambda: DummySettings())
    monkeypatch.setattr(cli.io_formats, "read_tracks", lambda _path: tracks)
    monkeypatch.setattr(cli.io_formats, "write_tracks", lambda written_tracks, path, fmt: captured.update(
        {"written_tracks": written_tracks, "write_path": path, "fmt": fmt}
    ))
    monkeypatch.setattr(cli, "ReccoBeatsClient", FakeClient)

    output_path = Path(tmp_path / "out.json")
    cli.enrich(input=Path(tmp_path / "in.json"), output=output_path, fmt=None)

    assert captured["client"] == "reccobeats"
    assert captured["written_tracks"] == tracks
    assert captured["write_path"] == output_path
    assert "Enriched 1/1 tracks with reccobeats" in capsys.readouterr().out


def test_enrich_uses_getgenre_when_requested(monkeypatch, capsys, tmp_path):
    tracks = [Track(spotify_id="abc", title="Song", artist="Artist", album="Album")]
    captured: dict = {}

    class FakeClient:
        def __init__(self, _settings):
            captured["client"] = "getgenre"

        def enrich(self, input_tracks):
            input_tracks[0].genre_source = "getgenre"
            input_tracks[0].genres = ["indie"]
            return input_tracks

    monkeypatch.setattr(cli, "load_settings", lambda: DummySettings())
    monkeypatch.setattr(cli.io_formats, "read_tracks", lambda _path: tracks)
    monkeypatch.setattr(cli.io_formats, "write_tracks", lambda written_tracks, path, fmt: captured.update(
        {"written_tracks": written_tracks, "write_path": path, "fmt": fmt}
    ))
    monkeypatch.setattr(cli, "GetGenreClient", FakeClient)

    output_path = Path(tmp_path / "out.json")
    cli.enrich(input=Path(tmp_path / "in.json"), output=output_path, fmt=None, api="getgenre")

    assert captured["client"] == "getgenre"
    assert captured["written_tracks"][0].genres == ["indie"]
    assert "Enriched 1/1 tracks with getgenre" in capsys.readouterr().out


def test_enrich_rejects_unknown_api(capsys, tmp_path):
    result = runner.invoke(
        cli.app,
        [
            "enrich",
            "--input",
            str(tmp_path / "in.json"),
            "--output",
            str(tmp_path / "out.json"),
            "--api",
            "unknown-api",
        ],
    )

    assert result.exit_code != 0
    assert "Invalid value for '--api'" in result.output
