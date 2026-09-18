from __future__ import annotations

from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from playlist_forge import cli
from playlist_forge.errors import AuthFailureError
from playlist_forge.io_formats import read_tracks, write_tracks
from playlist_forge.library.merge import merge_libraries, playlist_name_for_id
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


def test_config_getgenre_reports_written_path(monkeypatch, capsys):
    captured_args: dict = {}

    def fake_set_getgenre_credentials(username: str, password: str) -> Path:
        captured_args["username"] = username
        captured_args["password"] = password
        return Path("/tmp/config.json")

    monkeypatch.setattr(cli, "set_getgenre_credentials", fake_set_getgenre_credentials)
    monkeypatch.setattr(cli.typer, "prompt", lambda *_args, **_kwargs: "genre-pass")

    cli.config_getgenre("genre-user")

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
    assert playlist_name_for_id(t, "p-target") == "Target"


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

    cli.analyze_outliers(input=Path(tmp_path / "in.json"), playlist=["Target"], top_n=5)

    assert [track.spotify_id for track in captured["tracks"]] == ["t1"]
    assert captured["tracks"][0].playlist_ids == ["p-target"]
    assert captured["tracks"][0].playlist_names == ["Target"]
    assert "Target" in capsys.readouterr().out


def test_analyze_outliers_reports_when_filters_match_nothing(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli.io_formats, "read_tracks", lambda _path: [])
    monkeypatch.setattr(
        cli.outliers_mod,
        "top_outliers_by_playlist",
        lambda *_args, **_kwargs: pytest.fail("outlier analysis should not run"),
    )

    cli.analyze_outliers(input=Path(tmp_path / "in.json"), playlist=["Missing"], top_n=5)

    assert "No tracks matched the supplied --playlist filters." in capsys.readouterr().out


def test_analyze_dedupe_filters_duplicates_and_prunes_overlap_memberships(monkeypatch, tmp_path):
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
    monkeypatch.setattr(
        cli.dedupe_mod,
        "find_duplicate_tracks",
        lambda selected_tracks, threshold: captured.update(
            {"duplicate_tracks": selected_tracks, "track_threshold": threshold}
        )
        or [],
    )
    monkeypatch.setattr(
        cli.dedupe_mod,
        "find_playlist_overlaps",
        lambda selected_tracks, threshold: captured.update(
            {"overlap_tracks": selected_tracks, "playlist_threshold": threshold}
        )
        or [],
    )

    cli.analyze_dedupe(
        input=Path(tmp_path / "in.json"),
        output=Path(tmp_path / "out.json"),
        playlist=["Target"],
        track_threshold=0.9,
        playlist_threshold=0.6,
    )

    assert [track.spotify_id for track in captured["duplicate_tracks"]] == ["t1"]
    assert captured["duplicate_tracks"][0].playlist_ids == ["p-target", "p-other"]
    assert [track.spotify_id for track in captured["overlap_tracks"]] == ["t1"]
    assert captured["overlap_tracks"][0].playlist_ids == ["p-target"]


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
        playlist=None,
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
        playlist=None,
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


def test_library_merge_merges_playlists_genres_and_metadata(tmp_path):
    first_input = Path(tmp_path / "library_a.json")
    second_input = Path(tmp_path / "library_b.json")
    output_path = Path(tmp_path / "merged.json")

    write_tracks(
        [
            Track(
                spotify_id="shared",
                title="First Title",
                artist="First Artist",
                album="First Album",
                playlist_ids=["p1", "p2"],
                playlist_names=["Playlist One", "Playlist Two"],
                genres=["rock", "indie"],
                year=None,
                duration_ms=111000,
            ),
            Track(spotify_id="first-only", title="Only First", artist="A", album="B"),
        ],
        first_input,
    )
    write_tracks(
        [
            Track(
                spotify_id="shared",
                title="Second Title",
                artist="Second Artist",
                album="Second Album",
                playlist_ids=["p2", "p3"],
                playlist_names=["Different Name Ignored", "Playlist Three"],
                genres=["indie", "electronic"],
                year=2002,
                duration_ms=222000,
            ),
            Track(spotify_id="second-only", title="Only Second", artist="C", album="D"),
        ],
        second_input,
    )

    cli.library_merge(input=[first_input, second_input], output=output_path, fmt=None)
    merged = {track.spotify_id: track for track in read_tracks(output_path)}

    shared = merged["shared"]
    assert shared.title == "First Title"
    assert shared.artist == "First Artist"
    assert shared.album == "First Album"
    assert shared.duration_ms == 111000
    assert shared.year == 2002
    assert shared.playlist_ids == ["p1", "p2", "p3"]
    assert shared.playlist_names == ["Playlist One", "Playlist Two", "Playlist Three"]
    assert shared.genres == ["rock", "indie", "electronic"]
    assert set(merged.keys()) == {"shared", "first-only", "second-only"}


def test_library_merge_single_input_matches_convert_behavior(tmp_path):
    input_path = Path(tmp_path / "library.json")
    output_path = Path(tmp_path / "merged.json")

    write_tracks(
        [
            Track(spotify_id="dup", title="First", artist="A", album="X"),
            Track(spotify_id="dup", title="Second", artist="A", album="Y"),
        ],
        input_path,
    )

    cli.library_merge(input=[input_path], output=output_path, fmt=None)

    merged = read_tracks(output_path)
    assert [track.title for track in merged] == ["First", "Second"]


def test_library_merge_repeated_input_keeps_first_file_duplicates(tmp_path):
    input_path = Path(tmp_path / "library.json")
    output_path = Path(tmp_path / "merged.json")

    write_tracks(
        [
            Track(
                spotify_id="dup",
                title="First",
                artist="A",
                album="X",
                playlist_ids=["p1"],
                playlist_names=["One"],
                genres=["rock"],
                year=None,
            ),
            Track(
                spotify_id="dup",
                title="Second",
                artist="A",
                album="Y",
                playlist_ids=["p2"],
                playlist_names=["Two"],
                genres=["pop"],
                year=None,
            ),
        ],
        input_path,
    )

    cli.library_merge(input=[input_path, input_path], output=output_path, fmt=None)

    merged = read_tracks(output_path)
    assert [track.title for track in merged] == ["First", "Second"]
    assert merged[0].playlist_ids == ["p1"]
    assert merged[1].playlist_ids == ["p2"]


def test_library_merge_keeps_later_file_duplicate_rows(tmp_path):
    first_input = Path(tmp_path / "library_a.json")
    second_input = Path(tmp_path / "library_b.json")
    output_path = Path(tmp_path / "merged.json")

    write_tracks([Track(spotify_id="dup", title="A", artist="X", album="Y")], first_input)
    write_tracks(
        [
            Track(spotify_id="dup", title="B1", artist="X", album="Y", year=2001),
            Track(spotify_id="dup", title="B2", artist="X", album="Y", year=2002),
        ],
        second_input,
    )

    cli.library_merge(input=[first_input, second_input], output=output_path, fmt=None)

    merged = read_tracks(output_path)
    assert len(merged) == 2
    assert merged[0].year == 2001
    assert merged[1].title == "B2"


def test_library_merge_preserves_later_file_row_order_for_new_rows(tmp_path):
    first_input = Path(tmp_path / "library_a.json")
    second_input = Path(tmp_path / "library_b.json")
    output_path = Path(tmp_path / "merged.json")

    write_tracks([Track(spotify_id="dup", title="A", artist="X", album="Y")], first_input)
    write_tracks(
        [
            Track(spotify_id="dup", title="B1", artist="X", album="Y"),
            Track(spotify_id="new-1", title="N1", artist="X", album="Y"),
            Track(spotify_id="dup", title="B2", artist="X", album="Y"),
            Track(spotify_id="new-2", title="N2", artist="X", album="Y"),
        ],
        second_input,
    )

    cli.library_merge(input=[first_input, second_input], output=output_path, fmt=None)

    merged = read_tracks(output_path)
    assert [track.spotify_id for track in merged] == ["dup", "new-1", "dup", "new-2"]


def test_merge_libraries_rejects_empty_inputs():
    with pytest.raises(ValueError, match="At least one input path is required"):
        merge_libraries([])
