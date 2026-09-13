from __future__ import annotations

import pytest

from playlist_forge import auth
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


def test_logout_removes_cached_token(monkeypatch, tmp_path):
    token_path = tmp_path / "token.json"
    token_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(auth, "TOKEN_PATH", token_path)

    removed = auth.logout()

    assert removed is True
    assert not token_path.exists()


def test_logout_returns_false_when_no_cached_token(monkeypatch, tmp_path):
    token_path = tmp_path / "token.json"
    monkeypatch.setattr(auth, "TOKEN_PATH", token_path)

    removed = auth.logout()

    assert removed is False


def test_logout_returns_false_when_token_path_is_directory(monkeypatch, tmp_path):
    token_path = tmp_path / "token.json"
    token_path.mkdir()
    monkeypatch.setattr(auth, "TOKEN_PATH", token_path)

    with pytest.raises(ConfigurationError, match="Cached token path is not a file"):
        auth.logout()


def test_logout_raises_configuration_error_on_permission_error(monkeypatch):
    class NonDeletablePath:
        def exists(self):
            return True

        def is_file(self):
            return True

        def unlink(self):
            raise PermissionError("permission denied")

        def __str__(self):
            return "/fake/token.json"

    monkeypatch.setattr(auth, "TOKEN_PATH", NonDeletablePath())

    with pytest.raises(ConfigurationError, match="Could not remove cached token at /fake/token.json"):
        auth.logout()
