from __future__ import annotations

import pytest

from playlist_forge.auth import get_spotify_client
from playlist_forge.config import Settings
from playlist_forge.errors import ConfigurationError


def test_get_spotify_client_raises_configuration_error_when_client_id_missing():
    settings = Settings(
        spotify_client_id=None,
        spotify_client_secret=None,
        spotify_redirect_uri="http://127.0.0.1:8080/callback",
        reccobeats_api_key=None,
        config={},
    )

    with pytest.raises(ConfigurationError, match="SPOTIFY_CLIENT_ID is not set"):
        get_spotify_client(settings)
