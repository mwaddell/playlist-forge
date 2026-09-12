from __future__ import annotations

from pathlib import Path

import pytest
import typer

from playlist_forge import cli
from playlist_forge.errors import AuthFailureError
from playlist_forge.models import Track


class DummySettings:
    pass


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
