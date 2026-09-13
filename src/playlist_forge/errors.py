from __future__ import annotations


class PlaylistForgeError(RuntimeError):
    """Base error for expected, user-facing command failures."""


class ConfigurationError(PlaylistForgeError):
    """Required local configuration is missing or invalid."""


class AuthFailureError(PlaylistForgeError):
    """Authentication failed (401/invalid token)."""


class RateLimitExceededError(PlaylistForgeError):
    """Rate-limited too many times in a row."""


class NetworkFailureError(PlaylistForgeError):
    """Transient network failure that did not recover."""


class ExternalServiceError(PlaylistForgeError):
    """Non-auth/non-rate-limit upstream API failure."""
