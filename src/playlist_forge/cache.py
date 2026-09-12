"""Tiny sqlite-backed cache for enrichment lookups.

Keyed by ISRC (preferred) or a normalized title+artist string. Avoids
re-hitting ReccoBeats every time you re-run `enrich` while tuning things
downstream.
"""

from __future__ import annotations

import json
import sqlite3

from .config import CACHE_DIR

_DB_PATH = CACHE_DIR / "enrichment.sqlite3"


def _connect() -> sqlite3.Connection:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS reccobeats_cache ("
        "key TEXT PRIMARY KEY, payload TEXT NOT NULL)"
    )
    return conn


def get(key: str) -> dict | None:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT payload FROM reccobeats_cache WHERE key = ?", (key,)
        ).fetchone()
        return json.loads(row[0]) if row else None
    finally:
        conn.close()


def set(key: str, payload: dict) -> None:
    conn = _connect()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO reccobeats_cache (key, payload) VALUES (?, ?)",
            (key, json.dumps(payload)),
        )
        conn.commit()
    finally:
        conn.close()


def normalize_key(title: str, artist: str) -> str:
    return f"{title.strip().lower()}::{artist.strip().lower()}"
