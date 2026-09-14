"""Configuration loading and persistence."""

from __future__ import annotations

import copy
import json
import os
from dataclasses import dataclass
from pathlib import Path

from .errors import ConfigurationError

CONFIG_DIR = Path(os.environ.get("PLAYLIST_FORGE_HOME", Path.home() / ".config" / "playlist-forge"))
CACHE_DIR = CONFIG_DIR / "cache"
TOKEN_PATH = CONFIG_DIR / "token.json"
CONFIG_PATH = CONFIG_DIR / "config.json"
DEFAULT_REDIRECT_URI = "http://127.0.0.1:8080/callback"

_DEFAULTS = {
    "spotify": {
        "client_id": None,
        "redirect_uri": DEFAULT_REDIRECT_URI,
    },
    "cluster": {
        "genre_weight": 1.0,
        "audio_feature_weight": 1.0,
        "audio_acousticness_weight": None,
        "audio_danceability_weight": None,
        "audio_energy_weight": None,
        "audio_instrumentalness_weight": None,
        "audio_liveness_weight": None,
        "audio_loudness_weight": None,
        "audio_speechiness_weight": None,
        "audio_tempo_weight": None,
        "audio_valence_weight": None,
        "year_weight": 0.3,
    },
    "dedupe": {
        "title_artist_threshold": 0.90,
        "playlist_overlap_threshold": 0.60,
    },
    "reccobeats": {
        "base_url": "https://api.reccobeats.com",
        "request_delay_seconds": 0.2,
    },
}


@dataclass
class Settings:
    spotify_client_id: str | None
    spotify_redirect_uri: str
    reccobeats_api_key: str | None
    config: dict


def _merge_dicts(base: dict, override: dict) -> dict:
    """Recursively merge nested config dictionaries."""
    merged = copy.deepcopy(base)
    for key, value in override.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = _merge_dicts(current, value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def default_config() -> dict:
    """Return a deep copy of the built-in configuration defaults."""
    return copy.deepcopy(_DEFAULTS)


def write_config(config: dict) -> Path:
    """Write config data to the active config.json path."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return CONFIG_PATH


def _read_user_config() -> dict:
    """Read the raw user config JSON object from disk."""
    if not CONFIG_PATH.exists():
        return {}

    try:
        user_config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigurationError(f"Invalid JSON in config file {CONFIG_PATH}: {exc}") from exc

    if user_config is None:
        return {}
    if not isinstance(user_config, dict):
        raise ConfigurationError(f"Config file {CONFIG_PATH} must contain a JSON object.")
    return user_config


def load_config() -> dict:
    """Load config.json and merge it over the built-in defaults."""
    return _merge_dicts(_DEFAULTS, _read_user_config())


def initialize_config(*, force: bool = False) -> Path:
    """Create config.json, or replace it when ``force`` is true."""
    if CONFIG_PATH.exists() and not force:
        raise ConfigurationError(
            f"Config file already exists at {CONFIG_PATH}. Re-run with --force to replace it."
        )
    return write_config(default_config())


def _set_nested_config_value(config: dict, path: tuple[str, ...], value: object) -> dict:
    """Return config with one nested path updated."""
    current = config
    for key in path[:-1]:
        next_value = current.setdefault(key, {})
        if not isinstance(next_value, dict):
            dotted_path = ".".join(path[:-1])
            raise ConfigurationError(f"The {dotted_path} config section must be a JSON object.")
        current = next_value
    current[path[-1]] = value
    return config


def set_spotify_client_id(client_id: str) -> Path:
    """Persist the Spotify client ID in config.json."""
    normalized = client_id.strip()
    if not normalized:
        raise ConfigurationError("Spotify client ID cannot be empty.")

    return write_config(_set_nested_config_value(load_config(), ("spotify", "client_id"), normalized))


def load_settings() -> Settings:
    """Load application settings from config.json.

    Returns:
        Resolved Settings values for authentication and analysis defaults.
    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    merged = load_config()
    spotify_config = merged.get("spotify", {})
    reccobeats_config = merged.get("reccobeats", {})

    return Settings(
        spotify_client_id=spotify_config.get("client_id"),
        spotify_redirect_uri=spotify_config.get("redirect_uri", DEFAULT_REDIRECT_URI)
        or DEFAULT_REDIRECT_URI,
        reccobeats_api_key=reccobeats_config.get("api_key"),
        config=merged,
    )
