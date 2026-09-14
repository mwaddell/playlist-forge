"""Canonical data model shared by every pipeline stage.

Every module in playlist_forge (pull, enrich, analyze, push) reads and writes
Track / Playlist objects. This is what keeps json/csv/tsv interchangeable
and keeps the analysis code completely decoupled from the Spotify API.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any
import math


@dataclass
class Track:
    spotify_id: str
    title: str
    artist: str
    album: str
    playlist_ids: list[str] = field(default_factory=list)
    playlist_names: list[str] = field(default_factory=list)

    isrc: str | None = None
    year: int | None = None
    duration_ms: int | None = None
    added_at: str | None = None
    artist_genres: list[str] = field(default_factory=list)

    # Audio-feature enrichment (ReccoBeats or similar). All optional —
    # analysis code must degrade gracefully when these are None.
    tempo: float | None = None
    energy: float | None = None
    danceability: float | None = None
    valence: float | None = None
    acousticness: float | None = None
    instrumentalness: float | None = None
    liveness: float | None = None
    loudness: float | None = None
    speechiness: float | None = None

    # Provenance: be honest about where enrichment data came from, since
    # Spotify's own audio-features endpoint is deprecated for new apps.
    feature_source: str | None = None  # "reccobeats" | "unmatched" | None
    feature_match_confidence: float | None = None

    # Analysis output (populated by `analyze`, not `pull`)
    cluster_id: int | None = None
    outlier_score: float | None = None

    LIST_FIELDS = ("playlist_ids", "playlist_names", "artist_genres")

    def to_flat_dict(self, delimiter: str = ",") -> dict[str, Any]:
        """Flatten a track for CSV/TSV serialization.

        Args:
            delimiter: Delimiter used to join list-valued fields.

        Returns:
            Flat dictionary representation of the track.
        """
        out: dict[str, Any] = {}
        for f in fields(self):
            value = getattr(self, f.name)
            if f.name in self.LIST_FIELDS:
                out[f.name] = delimiter.join(value) if value else ""
            elif isinstance(value, float):
                out[f.name] = f"{value:.8f}" if value is not None and not math.isnan(value) else ""
            else:
                out[f.name] = value if value is not None else ""
        return out

    @classmethod
    def from_flat_dict(cls, row: dict[str, Any], delimiter: str = ",") -> Track:
        """Build a ``Track`` from a flat CSV/TSV row.

        Args:
            row: Flat dictionary row from CSV/TSV input.
            delimiter: Delimiter used inside flattened list-valued fields.

        Returns:
            Reconstructed ``Track`` instance.
        """
        kwargs: dict[str, Any] = {}
        valid_fields = {f.name for f in fields(cls)}
        for key, value in row.items():
            if key not in valid_fields:
                continue
            if key in cls.LIST_FIELDS:
                kwargs[key] = [v for v in (value or "").split(delimiter) if v]
            elif value in ("", None):
                kwargs[key] = None
            elif key in ("year", "duration_ms", "cluster_id"):
                kwargs[key] = int(value)
            elif key in (
                "tempo", "energy", "danceability", "valence",
                "acousticness", "instrumentalness", "liveness", 
                "loudness", "speechiness", "feature_match_confidence",
                "outlier_score",
            ):
                kwargs[key] = float(value)
            else:
                kwargs[key] = value
        return cls(**kwargs)


@dataclass
class Playlist:
    spotify_id: str
    name: str
    description: str | None = None
    track_count: int = 0
    owner: str | None = None
    owner_id: str | None = None
    is_collaborative: bool = False
