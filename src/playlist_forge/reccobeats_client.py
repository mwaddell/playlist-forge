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

import time

import requests

from . import cache
from .config import Settings
from .models import Track

FEATURE_FIELDS = (
    "tempo", "energy", "danceability", "valence",
    "acousticness", "instrumentalness",
)


class ReccoBeatsClient:
    def __init__(self, settings: Settings):
        self.base_url = settings.config["reccobeats"]["base_url"].rstrip("/")
        self.delay = settings.config["reccobeats"]["request_delay_seconds"]
        self.api_key = settings.reccobeats_api_key  # None is fine; free tier needs no key today
        self.session = requests.Session()
        if self.api_key:
            self.session.headers["Authorization"] = f"Bearer {self.api_key}"

    def _get(self, path: str, params: dict) -> dict | None:
        try:
            resp = self.session.get(f"{self.base_url}{path}", params=params, timeout=10)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            print(f"[reccobeats] request failed for {params}: {exc}")
            return None

    def fetch_by_spotify_id(self, spotify_id: str) -> dict | None:
        cache_key = f"spotify:{spotify_id}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached or None  # cache.get returns {} for a cached "no match"

        data = self._get("/v1/audio-features", params={"ids": spotify_id})
        time.sleep(self.delay)
        cache.set(cache_key, data or {})
        return data

    def enrich(self, tracks: list[Track]) -> list[Track]:
        """Mutates and returns `tracks` with audio-feature fields populated
        where a match was found. Tracks that don't match are left with
        feature_source="unmatched" so downstream analysis can filter them
        out (or weight them down) explicitly rather than silently treating
        a missing value as a real 0.0.
        """
        for t in tracks:
            payload = self.fetch_by_spotify_id(t.spotify_id)
            if not payload:
                t.feature_source = "unmatched"
                continue

            # NOTE: verify these keys against the current ReccoBeats response
            # shape (reccobeats.com/docs/apis/get-audio-features) — response
            # field names are not guaranteed to be stable across their versions.
            for field_name in FEATURE_FIELDS:
                if field_name in payload:
                    setattr(t, field_name, payload[field_name])
            t.feature_source = "reccobeats"
            t.feature_match_confidence = payload.get("confidence")
        return tracks
