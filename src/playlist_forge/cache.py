"""Tiny sqlite-backed cache for API lookups."""

from __future__ import annotations

import json
import sqlite3
from enum import Enum

from .config import CACHE_DIR


class CacheType(Enum):
    """Cache definitions for API lookups."""

    SPOTIFY = "spotify"
    RECCOBEATS = "reccobeats"
    GETGENRE = "getgenre"

def _connect(typ: CacheType) -> sqlite3.Connection:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    filetype = {
        CacheType.SPOTIFY: "library",
        CacheType.RECCOBEATS: "enrichment",
        CacheType.GETGENRE: "getgenre",
    }[typ]

    conn = sqlite3.connect(CACHE_DIR / f"{filetype}.sqlite3")
    conn.execute(f"CREATE TABLE IF NOT EXISTS {typ.value}_cache (key TEXT PRIMARY KEY, payload TEXT NOT NULL)")
    return conn


def get(typ: CacheType, key: str) -> dict | None:
    """Fetch a cached payload for a key.

    Args:
        key: Cache key to look up.

    Returns:
        The cached payload dictionary when present, otherwise None.
    """
    conn = _connect(typ)
    try:
        row = conn.execute(
            f"SELECT payload FROM {typ.value}_cache WHERE key = ?", 
            (key,)
        ).fetchone()
        return json.loads(row[0]) if row else None
    finally:
        conn.close()


def set(typ: CacheType, key: str, payload: dict) -> None:
    """Store or replace a cached payload by key.

    Args:
        key: Cache key to write.
        payload: JSON-serializable payload to persist.

    Returns:
        None.
    """
    conn = _connect(typ)
    try:
        conn.execute(
            f"INSERT OR REPLACE INTO {typ.value}_cache (key, payload) VALUES (?, ?)",
            (key, json.dumps(payload)),
        )
        conn.commit()
    finally:
        conn.close()
