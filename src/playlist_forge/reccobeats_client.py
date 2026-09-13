"""Audio-feature enrichment via the ReccoBeats API.

ReccoBeats resolves tracks by Spotify ID (or its own UUID), and exposes a
batch "get multiple audio features" endpoint plus a single-track lookup.
Since Spotify's own audio-features endpoint is deprecated for new API apps,
this is our stand-in — treat its output as approximate, not authoritative,
and always check reccobeats.com/docs for the current request shape before
relying on this in production: their param names have changed before and
may change again.

Docs: https://reccobeats.com/docs/apis/get-audio-features
"""

from __future__ import annotations

import sys
import time
from collections.abc import Iterable, Iterator
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import TypeVar

import requests

from . import cache
from .config import Settings
from .errors import (
    AuthFailureError,
    ExternalServiceError,
    NetworkFailureError,
    RateLimitExceededError,
)
from .models import Track

T = TypeVar("T")

try:
    from rich.progress import track as progress_track
except ImportError:  # pragma: no cover - fallback for minimal installs
    def progress_track(sequence: Iterable[T], *args: object, **kwargs: object) -> Iterator[T]:
        """Return an iterator over the input when Rich is unavailable."""
        _ = (args, kwargs)
        return iter(sequence)


def _maybe_progress_track(sequence: Iterable[T], description: str) -> Iterator[T]:
    """Show progress only for interactive terminals."""
    if not sys.stdout.isatty():
        return iter(sequence)
    return iter(progress_track(sequence, description=description))

FEATURE_FIELDS = (
    "tempo", "energy", "danceability", "valence",
    "acousticness", "instrumentalness", "liveness",
    "loudness", "speechiness"
)


class ReccoBeatsClient:
    def __init__(self, settings: Settings):
        self.base_url = settings.config["reccobeats"]["base_url"].rstrip("/")
        self.delay = settings.config["reccobeats"]["request_delay_seconds"]
        self.max_retries = 3
        self.base_backoff_seconds = 1.0
        self.api_key = settings.reccobeats_api_key  # None is fine; free tier needs no key today
        self.session = requests.Session()
        if self.api_key:
            self.session.headers["Authorization"] = "Bearer " + self.api_key

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

    def _get(self, path: str, params: dict) -> dict | None:
        for attempt in range(self.max_retries + 1):
            resp: requests.Response | None = None
            try:
                resp = self.session.get(f"{self.base_url}{path}", params=params, timeout=10)
                if resp.status_code == 404:
                    return None
                if resp.status_code == 401:
                    raise AuthFailureError(
                        "ReccoBeats authentication failed (401). "
                        "Check RECCOBEATS_API_KEY and retry."
                    )
                if resp.status_code == 429:
                    if attempt >= self.max_retries:
                        raise RateLimitExceededError(
                            "ReccoBeats rate limit persisted after retries. Please wait and retry."
                        )
                    delay = self._retry_after_seconds(resp) or (
                        self.base_backoff_seconds * (2**attempt)
                    )
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
                        "ReccoBeats request timed out or lost connection after retries."
                    ) from exc
                time.sleep(self.base_backoff_seconds * (2**attempt))
            except requests.HTTPError as exc:
                response = exc.response or resp
                if response is not None and response.status_code == 401:
                    raise AuthFailureError(
                        "ReccoBeats authentication failed (401). "
                        "Check RECCOBEATS_API_KEY and retry."
                    ) from exc
                if (
                    response is not None
                    and response.status_code == 429
                    and attempt < self.max_retries
                ):
                    delay = self._retry_after_seconds(response) or (
                        self.base_backoff_seconds * (2**attempt)
                    )
                    time.sleep(delay)
                    continue
                raise ExternalServiceError(
                    f"ReccoBeats request failed for {params}: {exc}"
                ) from exc
            except requests.RequestException as exc:
                raise NetworkFailureError(
                    f"ReccoBeats request failed due to network issue for {params}: {exc}"
                ) from exc

        raise NetworkFailureError(f"ReccoBeats request failed for {params}.")

    def fetch_by_spotify_id(self, spotify_id: str) -> dict | None:
        """Fetch and cache audio-feature payload for one Spotify track ID.

        Args:
            spotify_id: Spotify track ID.

        Returns:
            Audio-feature payload when matched, otherwise None.
        """
        cache_key = f"spotify:{spotify_id}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached or None  # cache.get returns {} for a cached "no match"

        data = self._get("/v1/audio-features", params={"ids": spotify_id})
        time.sleep(self.delay)
        cache.set(cache_key, data if data is not None else {})
        return data

    def enrich(self, tracks: list[Track]) -> list[Track]:
        """Populate audio-feature fields on tracks using ReccoBeats matches.

        Args:
            tracks: Tracks to enrich in place.

        Returns:
            The same list with feature fields and provenance updated. Tracks
            without a match are marked with ``feature_source="unmatched"`` so
            downstream analysis can treat missing values explicitly.
        """
        for t in _maybe_progress_track(tracks, description="Enriching tracks..."):
            payload = self.fetch_by_spotify_id(t.spotify_id)
            if not payload:
                t.feature_source = "unmatched"
                continue

            for field_name in FEATURE_FIELDS:
                if field_name in payload:
                    setattr(t, field_name, payload[field_name])
            t.feature_source = "reccobeats"
            t.feature_match_confidence = payload.get("confidence")
        return tracks
