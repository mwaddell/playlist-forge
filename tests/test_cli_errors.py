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


def test_select_tracks_by_playlist_prunes_memberships():
    tracks = [
        Track(
            spotify_id="t1",
            title="A",
            artist="X",
            album="",
            playlist_ids=["p-alpha", "p-beta"],
            playlist_names=["Alpha", "Beta"],
        ),
        Track(
            spotify_id="t2",
            title="B",
            artist="Y",
            album="",
            playlist_ids=["p-beta"],
            playlist_names=["Beta"],
        ),
    ]

    selected = cli._select_tracks_by_playlist(tracks, ["alp"], prune_memberships=True)

    assert [track.spotify_id for track in selected] == ["t1"]
    assert selected[0].playlist_ids == ["p-alpha"]
    assert selected[0].playlist_names == ["Alpha"]
    assert tracks[0].playlist_ids == ["p-alpha", "p-beta"]


def test_pull_accepts_repeated_playlist_options(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "load_settings", lambda: DummySettings())
    monkeypatch.setattr(cli.auth, "get_spotify_client", lambda _settings: object())
    captured: dict = {}
    monkeypatch.setattr(
        cli.spotify_client,
        "pull_library",
        lambda _spotify, playlist_filters=None, force=False: captured.update(
            {"playlist_filters": playlist_filters, "force": force}
        )
        or [],
    )
    monkeypatch.setattr(cli.io_formats, "write_tracks", lambda *_args, **_kwargs: None)

    result = runner.invoke(
        cli.app,
        [
            "pull",
            "--output",
            str(tmp_path / "out.json"),
            "--playlist",
            "Road Trip",
            "--playlist",
            "37i9dQZF1DXcBWIGoYBM5M",
        ],
    )

    assert result.exit_code == 0
    assert captured["playlist_filters"] == ["Road Trip", "37i9dQZF1DXcBWIGoYBM5M"]
    assert captured["force"] is False


def test_enrich_only_updates_filtered_tracks(monkeypatch, tmp_path):
    tracks = [
        Track(
            spotify_id="t1",
            title="A",
            artist="X",
            album="",
            playlist_ids=["p-target"],
            playlist_names=["Target"],
        ),
        Track(
            spotify_id="t2",
            title="B",
            artist="Y",
            album="",
            playlist_ids=["p-other"],
            playlist_names=["Other"],
        ),
    ]

    class FakeClient:
        def __init__(self, _settings):
            pass

        def enrich(self, selected_tracks):
            for track in selected_tracks:
                track.feature_source = "reccobeats"
            return selected_tracks

    written: dict = {}
    monkeypatch.setattr(cli, "load_settings", lambda: DummySettings())
    monkeypatch.setattr(cli.io_formats, "read_tracks", lambda _path: tracks)
    monkeypatch.setattr(
        cli.io_formats,
        "write_tracks",
        lambda written_tracks, path, fmt: written.update(
            {"tracks": written_tracks, "path": path, "fmt": fmt}
        ),
    )
    monkeypatch.setattr(cli, "ReccoBeatsClient", FakeClient)

    cli.enrich(
        input=Path(tmp_path / "in.json"),
        output=Path(tmp_path / "out.json"),
        fmt=None,
        playlist=["Target"],
    )

    assert written["tracks"] == tracks
    assert tracks[0].feature_source == "reccobeats"
    assert tracks[1].feature_source is None


def test_analyze_cluster_only_updates_selected_tracks(monkeypatch, tmp_path):
    selected = Track(
        spotify_id="t1",
        title="A",
        artist="X",
        album="",
        playlist_ids=["p-target"],
        playlist_names=["Target"],
        cluster_id=9,
    )
    untouched = Track(
        spotify_id="t2",
        title="B",
        artist="Y",
        album="",
        playlist_ids=["p-other"],
        playlist_names=["Other"],
        cluster_id=7,
    )
    tracks = [selected, untouched]
    written: dict = {}
    captured_cluster_tracks: dict = {}

    monkeypatch.setattr(cli, "load_settings", lambda: DummySettings())
    monkeypatch.setattr(cli.io_formats, "read_tracks", lambda _path: tracks)
    monkeypatch.setattr(
        cli.io_formats,
        "write_tracks",
        lambda written_tracks, path, fmt: written.update(
            {"tracks": written_tracks, "path": path, "fmt": fmt}
        ),
    )

    def fake_cluster_kmeans(input_tracks, **kwargs):
        captured_cluster_tracks["tracks"] = input_tracks
        captured_cluster_tracks["kwargs"] = kwargs
        input_tracks[0].cluster_id = 3
        return input_tracks

    monkeypatch.setattr(cli.cluster_mod, "cluster_kmeans", fake_cluster_kmeans)

    cli.analyze_cluster(
        input=Path(tmp_path / "in.json"),
        output=Path(tmp_path / "out.json"),
        fmt=None,
        playlist=["Target"],
        algorithm="kmeans",
        k="auto",
    )

    assert captured_cluster_tracks["tracks"] == [selected]
    assert written["tracks"] == tracks
    assert selected.cluster_id == 3
    assert untouched.cluster_id is None


def test_analyze_outliers_filters_and_prunes_playlist_memberships(monkeypatch, tmp_path, capsys):
    tracks = [
        Track(
            spotify_id="t1",
            title="A",
            artist="X",
            album="",
            playlist_ids=["p-target", "p-other"],
            playlist_names=["Target", "Other"],
        ),
        Track(
            spotify_id="t2",
            title="B",
            artist="Y",
            album="",
            playlist_ids=["p-other"],
            playlist_names=["Other"],
        ),
    ]
    captured: dict = {}

    monkeypatch.setattr(cli.io_formats, "read_tracks", lambda _path: tracks)

    def fake_top_outliers_by_playlist(selected_tracks, top_n):
        captured["tracks"] = selected_tracks
        assert top_n == 5
        return {"p-target": [(selected_tracks[0], 0.25)]}

    monkeypatch.setattr(cli.outliers_mod, "top_outliers_by_playlist", fake_top_outliers_by_playlist)

    cli.analyze_outliers(input=Path(tmp_path / "in.json"), playlist=["Target"])

    assert [track.spotify_id for track in captured["tracks"]] == ["t1"]
    assert captured["tracks"][0].playlist_ids == ["p-target"]
    assert captured["tracks"][0].playlist_names == ["Target"]
    assert "Target" in capsys.readouterr().out


def test_push_merge_accepts_repeated_playlist_options(monkeypatch):
    monkeypatch.setattr(cli, "load_settings", lambda: DummySettings())
    monkeypatch.setattr(cli.auth, "get_spotify_client", lambda _settings: object())
    captured: dict = {}
    monkeypatch.setattr(
        cli.merge_playlists,
        "merge",
        lambda _spotify, playlist_names, into, dry_run=False: captured.update(
            {"playlist_names": playlist_names, "into": into, "dry_run": dry_run}
        )
        or "new-playlist-id",
    )

    result = runner.invoke(
        cli.app,
        [
            "push",
            "merge",
            "--playlist",
            "Chill 1",
            "--playlist",
            "Chill 2",
            "--into",
            "Chill (merged)",
            "--dry-run",
        ],
    )

    assert result.exit_code == 0
    assert captured == {
        "playlist_names": ["Chill 1", "Chill 2"],
        "into": "Chill (merged)",
        "dry_run": True,
    }


def test_push_merge_allows_no_source_playlists(monkeypatch):
    monkeypatch.setattr(cli, "load_settings", lambda: DummySettings())
    monkeypatch.setattr(cli.auth, "get_spotify_client", lambda _settings: object())
    captured: dict = {}
    monkeypatch.setattr(
        cli.merge_playlists,
        "merge",
        lambda _spotify, playlist_names, into, dry_run=False: captured.update(
            {"playlist_names": playlist_names, "into": into, "dry_run": dry_run}
        )
        or "new-playlist-id",
    )

    result = runner.invoke(cli.app, ["push", "merge", "--into", "Empty Playlist"])

    assert result.exit_code == 0
    assert captured == {
        "playlist_names": [],
        "into": "Empty Playlist",
        "dry_run": False,
    }


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
