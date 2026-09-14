from __future__ import annotations

import json

import pytest

from playlist_forge import config
from playlist_forge.errors import ConfigurationError


def test_initialize_config_writes_default_json(monkeypatch, tmp_path):
    config_dir = tmp_path / "config-home"
    config_path = config_dir / "config.json"
    cache_dir = config_dir / "cache"
    token_path = config_dir / "token.json"
    monkeypatch.setattr(config, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(config, "CONFIG_PATH", config_path)
    monkeypatch.setattr(config, "CACHE_DIR", cache_dir)
    monkeypatch.setattr(config, "TOKEN_PATH", token_path)

    written_path = config.initialize_config()

    assert written_path == config_path
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    assert payload["spotify"]["client_id"] is None
    assert payload["spotify"]["redirect_uri"] == "http://127.0.0.1:8080/callback"
    assert payload["cluster"]["genre_weight"] == 1.0


def test_initialize_config_requires_force_to_replace(monkeypatch, tmp_path):
    config_dir = tmp_path / "config-home"
    config_path = config_dir / "config.json"
    monkeypatch.setattr(config, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(config, "CONFIG_PATH", config_path)
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path.write_text('{"spotify":{"client_id":"existing"}}', encoding="utf-8")

    with pytest.raises(ConfigurationError, match="Re-run with --force"):
        config.initialize_config()

    written_path = config.initialize_config(force=True)

    assert written_path == config_path
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    assert payload["spotify"]["client_id"] is None


def test_load_settings_reads_spotify_values_from_config_json(monkeypatch, tmp_path):
    config_dir = tmp_path / "config-home"
    config_path = config_dir / "config.json"
    cache_dir = config_dir / "cache"
    token_path = config_dir / "token.json"
    monkeypatch.setattr(config, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(config, "CONFIG_PATH", config_path)
    monkeypatch.setattr(config, "CACHE_DIR", cache_dir)
    monkeypatch.setattr(config, "TOKEN_PATH", token_path)
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(
            {
                "spotify": {
                    "client_id": "spotify-client-id",
                    "redirect_uri": "http://localhost:9000/callback",
                },
                "reccobeats": {"api_key": "rb-key"},
                "cluster": {"genre_weight": 1.5},
            }
        ),
        encoding="utf-8",
    )

    settings = config.load_settings()

    assert settings.spotify_client_id == "spotify-client-id"
    assert settings.spotify_redirect_uri == "http://localhost:9000/callback"
    assert settings.reccobeats_api_key == "rb-key"
    assert settings.config["cluster"]["genre_weight"] == 1.5
    assert settings.config["cluster"]["year_weight"] == 0.3


def test_load_settings_rejects_directory_config_path(monkeypatch, tmp_path):
    config_dir = tmp_path / "config-home"
    config_path = config_dir / "config.json"
    cache_dir = config_dir / "cache"
    token_path = config_dir / "token.json"
    monkeypatch.setattr(config, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(config, "CONFIG_PATH", config_path)
    monkeypatch.setattr(config, "CACHE_DIR", cache_dir)
    monkeypatch.setattr(config, "TOKEN_PATH", token_path)
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path.mkdir()

    with pytest.raises(ConfigurationError, match="Could not read config file"):
        config.load_settings()


def test_set_spotify_client_id_updates_existing_config(monkeypatch, tmp_path):
    config_dir = tmp_path / "config-home"
    config_path = config_dir / "config.json"
    cache_dir = config_dir / "cache"
    token_path = config_dir / "token.json"
    monkeypatch.setattr(config, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(config, "CONFIG_PATH", config_path)
    monkeypatch.setattr(config, "CACHE_DIR", cache_dir)
    monkeypatch.setattr(config, "TOKEN_PATH", token_path)
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps({"cluster": {"genre_weight": 2.0}}),
        encoding="utf-8",
    )

    written_path = config.set_spotify_client_id(" new-client-id ")

    assert written_path == config_path
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    assert payload["spotify"]["client_id"] == "new-client-id"
    assert payload["cluster"]["genre_weight"] == 2.0
    assert payload["dedupe"]["title_artist_threshold"] == 0.9


def test_set_spotify_client_id_rejects_non_object_spotify_section(monkeypatch, tmp_path):
    config_dir = tmp_path / "config-home"
    config_path = config_dir / "config.json"
    monkeypatch.setattr(config, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(config, "CONFIG_PATH", config_path)
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path.write_text('{"spotify":"broken"}', encoding="utf-8")

    with pytest.raises(ConfigurationError, match="spotify config section must be a JSON object"):
        config.set_spotify_client_id("client-id")


def test_load_settings_rejects_non_object_spotify_section(monkeypatch, tmp_path):
    config_dir = tmp_path / "config-home"
    config_path = config_dir / "config.json"
    cache_dir = config_dir / "cache"
    token_path = config_dir / "token.json"
    monkeypatch.setattr(config, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(config, "CONFIG_PATH", config_path)
    monkeypatch.setattr(config, "CACHE_DIR", cache_dir)
    monkeypatch.setattr(config, "TOKEN_PATH", token_path)
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path.write_text('{"spotify":"broken"}', encoding="utf-8")

    with pytest.raises(ConfigurationError, match="spotify config section must be a JSON object"):
        config.load_settings()


def test_set_spotify_client_id_creates_full_default_config_when_missing(monkeypatch, tmp_path):
    config_dir = tmp_path / "config-home"
    config_path = config_dir / "config.json"
    monkeypatch.setattr(config, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(config, "CONFIG_PATH", config_path)

    config.set_spotify_client_id("client-id")

    payload = json.loads(config_path.read_text(encoding="utf-8"))
    assert payload["spotify"]["client_id"] == "client-id"
    assert payload["cluster"]["genre_weight"] == 1.0
    assert payload["reccobeats"]["base_url"] == "https://api.reccobeats.com"


def test_set_spotify_client_id_rejects_blank_values():
    with pytest.raises(ConfigurationError, match="cannot be empty"):
        config.set_spotify_client_id("   ")
