"""Read/write Track collections as json, csv, or tab-delimited files.

Every other module only ever touches list[Track]. This is the only place
that knows about file formats, so adding a new format later (e.g. parquet)
means touching exactly one file.
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path

from .models import Track

_DELIMS = {"csv": ",", "tsv": "\t", "tab": "\t", "txt": "\t"}


def infer_format(path: str | Path) -> str:
    """Infer the track file format from a path suffix.

    Args:
        path: Target file path.

    Returns:
        One of ``json``, ``tsv``, or ``csv``.
    """
    suffix = Path(path).suffix.lower().lstrip(".")
    if suffix in ("json",):
        return "json"
    if suffix in ("tsv", "tab", "txt"):
        return "tsv"
    return "csv"


def write_tracks(tracks: list[Track], path: str | Path, fmt: str | None = None) -> None:
    """Write tracks to a JSON/CSV/TSV file.

    Args:
        tracks: Tracks to serialize.
        path: Output file path.
        fmt: Optional explicit format override.

    Returns:
        None.
    """
    path = Path(path)
    fmt = fmt or infer_format(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if fmt == "json":
        payload = [asdict(t) for t in tracks]
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return

    delimiter = _DELIMS.get(fmt, ",")
    if not tracks:
        path.write_text("", encoding="utf-8")
        return
    rows = [t.to_flat_dict(delimiter=";") for t in tracks]  # ';' inside list fields
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()), delimiter=delimiter)
        writer.writeheader()
        writer.writerows(rows)


def read_tracks(path: str | Path, fmt: str | None = None) -> list[Track]:
    """Read tracks from a JSON/CSV/TSV file.

    Args:
        path: Input file path.
        fmt: Optional explicit format override.

    Returns:
        Parsed track records.
    """
    path = Path(path)
    fmt = fmt or infer_format(path)

    if fmt == "json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        return [Track.from_dict(row) for row in payload]

    delimiter = _DELIMS.get(fmt, ",")
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh, delimiter=delimiter)
        return [Track.from_flat_dict(row, delimiter=";") for row in reader]
