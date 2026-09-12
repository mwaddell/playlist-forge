"""Configuration loading.

Secrets (Spotify client id/secret, ReccoBeats key) come from environment
variables / .env — never from the committed config file. Non-secret defaults
(clustering weights, default output format) live in config.yaml.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv

CONFIG_DIR = Path(os.environ.get("PLAYLIST_FORGE_HOME", Path.home() / ".config" / "playlist-forge"))
CACHE_DIR = CONFIG_DIR / "cache"
TOKEN_PATH = CONFIG_DIR / "token.json"
DEFAULT_CONFIG_PATH = CONFIG_DIR / "config.yaml"

_DEFAULTS = {
    "default_format": "json",
    "cluster": {
        "genre_weight": 1.0,
        "audio_feature_weight": 1.0,
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


def load_settings() -> Settings:
    """Load environment and file-backed application settings.

    Args:
        None.

    Returns:
        Resolved Settings values for authentication and analysis defaults.
    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    load_dotenv()  # loads .env from cwd if present

    user_config = {}
    if DEFAULT_CONFIG_PATH.exists():
        user_config = yaml.safe_load(DEFAULT_CONFIG_PATH.read_text()) or {}
    merged = {**_DEFAULTS, **user_config}

    return Settings(
        spotify_client_id=os.environ.get("SPOTIFY_CLIENT_ID"),
        spotify_client_secret=os.environ.get("SPOTIFY_CLIENT_SECRET"),
        spotify_redirect_uri=os.environ.get(
            "SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8080/callback"
        ),
        reccobeats_api_key=os.environ.get("RECCOBEATS_API_KEY"),
        config=merged,
    )
