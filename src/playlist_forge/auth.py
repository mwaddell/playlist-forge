"""Spotify OAuth (Authorization Code + PKCE) via spotipy."""

from __future__ import annotations

import spotipy
from spotipy.oauth2 import SpotifyPKCE

from .config import TOKEN_PATH, Settings
from .errors import ConfigurationError

SCOPES = [
    "playlist-read-private",
    "playlist-read-collaborative",
    "playlist-modify-private",
    "playlist-modify-public",
    "user-library-read",
]


def get_spotify_client(settings: Settings) -> spotipy.Spotify:
    """Create an authenticated Spotify client.

    Args:
        settings: Loaded application settings with Spotify OAuth configuration.

    Returns:
        An authenticated spotipy client instance.
    """
    if not settings.spotify_client_id:
        raise ConfigurationError(
            "SPOTIFY_CLIENT_ID is not set. Create an app at "
            "https://developer.spotify.com/dashboard, then set "
            "SPOTIFY_CLIENT_ID (and SPOTIFY_REDIRECT_URI if you changed it) "
            "in your environment or .env file."
        )

    auth_manager = SpotifyPKCE(
        client_id=settings.spotify_client_id,
        redirect_uri=settings.spotify_redirect_uri,
        scope=" ".join(SCOPES),
        cache_path=str(TOKEN_PATH),
        open_browser=True,
    )
    return spotipy.Spotify(auth_manager=auth_manager)


def login(settings: Settings) -> None:
    """Run OAuth login and cache a Spotify access token.

    Args:
        settings: Loaded application settings with Spotify OAuth configuration.

    Returns:
        None.
    """
    client = get_spotify_client(settings)
    me = client.current_user()
    print(f"Logged in as {me['display_name']} ({me['id']}). Token cached at {TOKEN_PATH}.")
