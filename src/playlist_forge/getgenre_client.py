"""Genre enrichment via the GetGenre API."""

from __future__ import annotations

import sys
import time
from collections.abc import Iterable, Iterator
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, TypeVar

import requests

from . import cache
from .config import Settings
from .errors import (
    AuthFailureError,
    ConfigurationError,
    ExternalServiceError,
    NetworkFailureError,
    RateLimitExceededError,
)
from .models import Track

T = TypeVar("T")


def _fallback_progress_track(sequence: Iterable[T], *args: object, **kwargs: object) -> Iterator[T]:
    """Return an iterator over the input when Rich is unavailable."""
    _ = (args, kwargs)
    return iter(sequence)


try:
    from rich.progress import track as progress_track
except ImportError:  # pragma: no cover - fallback for minimal installs
    progress_track = _fallback_progress_track


def _maybe_progress_track(sequence: Iterable[T], description: str) -> Iterator[T]:
    """Show progress only for interactive terminals."""
    if not getattr(sys.stdout, "isatty", lambda: False)():
        return iter(sequence)
    return iter(progress_track(sequence, description=description))


class GetGenreClient:
    def __init__(self, settings: Settings):
        config = settings.config["getgenre"]
        self.base_url = config["base_url"].rstrip("/")
        self.delay = config["request_delay_seconds"]
        self.timeout_seconds = config.get("timeout_seconds", 10)
        self.max_retries = 3
        self.base_backoff_seconds = 1.0
        self.username = settings.getgenre_username
        self.password = settings.getgenre_password
        self.session = requests.Session()
        self.session.headers["accept"] = "application/json"
        self._authenticated = False

    @staticmethod
    def _retry_after_seconds(resp: requests.Response) -> float | None:
        raw = resp.headers.get("Retry-After") or resp.headers.get("retry-after")
        if not raw:
            return None
        try:
            return max(float(raw), 0.0)
        except (TypeError, ValueError):
            pass
        try:
            retry_at = parsedate_to_datetime(raw)
        except (TypeError, ValueError):
            return None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)
        return max((retry_at - datetime.now(timezone.utc)).total_seconds(), 0.0)

    def _authenticate(self) -> None:
        if self._authenticated:
            return
        if not self.username or not self.password:
            raise ConfigurationError(
                "GetGenre credentials are not configured. "
                "Set getgenre.username and getgenre.password in config.json and retry."
            )

        payload = {
            "grant_type": "password",
            "username": self.username,
            "password": self.password,
            "remember_me": "true",
            "refresh_token": "",
        }
        headers = {
            "accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        for attempt in range(self.max_retries + 1):
            resp: requests.Response | None = None
            try:
                resp = self.session.post(
                    f"{self.base_url}/token",
                    data=payload,
                    headers=headers,
                    timeout=self.timeout_seconds,
                )
                if resp.status_code == 401:
                    raise AuthFailureError(
                        "GetGenre authentication failed (401). "
                        "Check getgenre.username and getgenre.password in config.json and retry."
                    )
                if resp.status_code == 429:
                    if attempt >= self.max_retries:
                        raise RateLimitExceededError(
                            "GetGenre rate limit persisted after retries. Please wait and retry."
                        )
                    delay = self._retry_after_seconds(resp) or (self.base_backoff_seconds * (2**attempt))
                    time.sleep(delay)
                    continue
                if resp.status_code >= 500 and attempt < self.max_retries:
                    time.sleep(self.base_backoff_seconds * (2**attempt))
                    continue
                resp.raise_for_status()
                data = resp.json()
                access_token = data.get("access_token")
                token_type = data.get("token_type") or "Bearer"
                if not access_token:
                    raise ExternalServiceError("GetGenre token response did not include an access token.")
                self.session.headers["Authorization"] = f"{token_type} {access_token}"
                self._authenticated = True
                return
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
                if attempt >= self.max_retries:
                    raise NetworkFailureError(
                        "GetGenre authentication timed out or lost connection after retries."
                    ) from exc
                time.sleep(self.base_backoff_seconds * (2**attempt))
            except requests.HTTPError as exc:
                response = exc.response or resp
                if response is not None and response.status_code == 401:
                    raise AuthFailureError(
                        "GetGenre authentication failed (401). "
                        "Check getgenre.username and getgenre.password in config.json and retry."
                    ) from exc
                if response is not None and response.status_code == 429 and attempt < self.max_retries:
                    delay = self._retry_after_seconds(response) or (self.base_backoff_seconds * (2**attempt))
                    time.sleep(delay)
                    continue
                raise ExternalServiceError(f"GetGenre authentication failed: {exc}") from exc
            except requests.RequestException as exc:
                raise NetworkFailureError(f"GetGenre authentication failed due to network issue: {exc}") from exc

        raise NetworkFailureError("GetGenre authentication failed.")

    def _get(self, params: dict[str, Any]) -> dict | None:
        self._authenticate()
        for attempt in range(self.max_retries + 1):
            resp: requests.Response | None = None
            try:
                resp = self.session.get(
                    f"{self.base_url}/search",
                    params=params,
                    timeout=self.timeout_seconds,
                )
                if resp.status_code == 404:
                    return None
                if resp.status_code == 401:
                    self._authenticated = False
                    self.session.headers.pop("Authorization", None)
                    if attempt >= self.max_retries:
                        raise AuthFailureError(
                            "GetGenre authentication failed (401). "
                            "Check getgenre.username and getgenre.password in config.json and retry."
                        )
                    self._authenticate()
                    continue
                if resp.status_code == 202 and attempt < self.max_retries:
                    delay = self._retry_after_seconds(resp) or (self.base_backoff_seconds * (2**attempt))
                    time.sleep(delay)
                    continue
                if resp.status_code == 202:
                    raise ExternalServiceError(
                        "GetGenre lookup did not finish after retries. Please wait and retry."
                    )
                if resp.status_code == 429:
                    if attempt >= self.max_retries:
                        raise RateLimitExceededError(
                            "GetGenre rate limit persisted after retries. Please wait and retry."
                        )
                    delay = self._retry_after_seconds(resp) or (self.base_backoff_seconds * (2**attempt))
                    time.sleep(delay)
                    continue
                if resp.status_code >= 500 and attempt < self.max_retries:
                    time.sleep(self.base_backoff_seconds * (2**attempt))
                    continue
                resp.raise_for_status()
                return resp.json()
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
                if attempt >= self.max_retries:
                    raise NetworkFailureError(
                        "GetGenre request timed out or lost connection after retries."
                    ) from exc
                time.sleep(self.base_backoff_seconds * (2**attempt))
            except requests.HTTPError as exc:
                response = exc.response or resp
                if response is not None and response.status_code == 401:
                    self._authenticated = False
                    self.session.headers.pop("Authorization", None)
                    if attempt >= self.max_retries:
                        raise AuthFailureError(
                            "GetGenre authentication failed (401). "
                            "Check getgenre.username and getgenre.password in config.json and retry."
                        ) from exc
                    self._authenticate()
                    continue
                if response is not None and response.status_code == 429 and attempt < self.max_retries:
                    delay = self._retry_after_seconds(response) or (self.base_backoff_seconds * (2**attempt))
                    time.sleep(delay)
                    continue
                raise ExternalServiceError(f"GetGenre request failed for {params}: {exc}") from exc
            except requests.RequestException as exc:
                raise NetworkFailureError(
                    f"GetGenre request failed due to network issue for {params}: {exc}"
                ) from exc

        raise NetworkFailureError(f"GetGenre request failed for {params}.")

    @staticmethod
    def _cache_key(prefix: str, *parts: str) -> str:
        normalized = [prefix]
        normalized.extend(part.strip().casefold() for part in parts if part and part.strip())
        return ":".join(normalized)

    def _search_with_cache(self, cache_key: str, params: dict[str, Any]) -> dict | None:
        cached = cache.get(cache.CacheType.GETGENRE, cache_key)
        if cached is not None:
            return cached or None

        data = self._get(params)
        time.sleep(self.delay)
        cache.set(cache.CacheType.GETGENRE, cache_key, data if data is not None else {})
        return data

    def fetch_by_track(self, title: str, artist: str = "") -> dict | None:
        """Fetch and cache a GetGenre result for a track lookup."""
        params: dict[str, Any] = {"track_name": title, "timeout": self.timeout_seconds}
        if artist:
            params["artist_name"] = artist
        return self._search_with_cache(self._cache_key("track", title, artist), params)

    def fetch_by_artist(self, artist: str) -> dict | None:
        """Fetch and cache a GetGenre result for an artist lookup."""
        params: dict[str, Any] = {"artist_name": artist, "timeout": self.timeout_seconds}
        return self._search_with_cache(self._cache_key("artist", artist), params)

    @staticmethod
    def _extract_genres(payload: dict | None) -> list[str]:
        if not payload:
            return []
        genres: list[str] = []
        for key in ("top_genres", "genres"):
            value = payload.get(key, [])
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, str) and item and item not in genres:
                        genres.append(item)
        return genres

    @staticmethod
    def _extract_confidence(payload: dict | None) -> float | None:
        if not payload:
            return None
        for key in ("genre_match_confidence", "match_confidence", "confidence", "score", "probability"):
            value = payload.get(key)
            if isinstance(value, (int, float)):
                return float(value)
        return None

    def enrich(self, tracks: list[Track]) -> list[Track]:
        """Populate track genres using GetGenre matches."""
        for track in _maybe_progress_track(tracks, description="Enriching tracks..."):
            payload = self.fetch_by_track(track.title, track.artist)
            genres = self._extract_genres(payload)
            if not genres and track.artist:
                payload = self.fetch_by_artist(track.artist)
                genres = self._extract_genres(payload)

            if not genres:
                track.genre_source = "unmatched"
                track.genre_match_confidence = None
                continue

            track.genres = genres
            track.genre_source = "getgenre"
            track.genre_match_confidence = self._extract_confidence(payload)
        return tracks
