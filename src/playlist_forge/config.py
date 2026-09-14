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
    spotify_client_secret: str | None
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


def load_config() -> dict:
    """Load config.json and merge it over the built-in defaults."""
    if not CONFIG_PATH.exists():
        return default_config()

    try:
        user_config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigurationError(f"Invalid JSON in config file {CONFIG_PATH}: {exc}") from exc

    if user_config is None:
        user_config = {}
    if not isinstance(user_config, dict):
        raise ConfigurationError(f"Config file {CONFIG_PATH} must contain a JSON object.")
    return _merge_dicts(_DEFAULTS, user_config)


def initialize_config() -> Path:
    """Create or replace config.json with the default values."""
    return write_config(default_config())


def set_spotify_client_id(client_id: str) -> Path:
    """Persist the Spotify client ID in config.json."""
    normalized = client_id.strip()
    if not normalized:
        raise ConfigurationError("Spotify client ID cannot be empty.")

    config = load_config()
    spotify_config = config.setdefault("spotify", {})
    if not isinstance(spotify_config, dict):
        raise ConfigurationError("The spotify config section must be a JSON object.")
    spotify_config["client_id"] = normalized
    return write_config(config)


def load_settings() -> Settings:
    """Load environment and file-backed application settings.

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
        spotify_client_secret=spotify_config.get("client_secret"),
        spotify_redirect_uri=spotify_config.get("redirect_uri", DEFAULT_REDIRECT_URI)
        or DEFAULT_REDIRECT_URI,
        reccobeats_api_key=reccobeats_config.get("api_key"),
        config=merged,
    )
