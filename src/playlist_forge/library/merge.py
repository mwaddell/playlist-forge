from __future__ import annotations

import copy
from dataclasses import fields as dataclass_fields
from pathlib import Path

from .. import io_formats
from ..models import Track


def playlist_name_for_id(track: Track, playlist_id: str) -> str:
    """Return the playlist name corresponding to a playlist id on a track.

    Args:
        track: Track-like object containing playlist ids and names.
        playlist_id: Playlist ID to resolve.

    Returns:
        Matching playlist name when available, otherwise the playlist id.
    """
    for idx, pid in enumerate(track.playlist_ids):
        if pid == playlist_id and idx < len(track.playlist_names):
            return track.playlist_names[idx]
    return playlist_id


def _merge_unique_strings(existing: list[str], incoming: list[str]) -> list[str]:
    seen = set(existing)
    merged = list(existing)
    for value in incoming:
        if value not in seen:
            seen.add(value)
            merged.append(value)
    return merged


def _playlist_membership_pairs(track: Track) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for pid in track.playlist_ids:
        pairs.append((pid, playlist_name_for_id(track, pid)))
    return pairs


def _merge_track_metadata(existing: Track, incoming: Track) -> None:
    playlist_name_by_id = dict(_playlist_membership_pairs(existing))
    for pid, pname in _playlist_membership_pairs(incoming):
        playlist_name_by_id.setdefault(pid, pname)
    existing.playlist_ids = list(playlist_name_by_id.keys())
    existing.playlist_names = list(playlist_name_by_id.values())
    existing.genres = _merge_unique_strings(existing.genres, incoming.genres)

    for field in dataclass_fields(existing):
        if field.name in {"spotify_id", "playlist_ids", "playlist_names", "genres"}:
            continue
        if getattr(existing, field.name) is None and getattr(incoming, field.name) is not None:
            setattr(existing, field.name, getattr(incoming, field.name))


def merge_libraries(inputs: list[Path]) -> list[Track]:
    """Merge one or more library track files into a single track list.

    Args:
        inputs: Input track dataset paths in precedence order.

    Returns:
        Merged track list.
    """
    if not inputs:
        raise ValueError("At least one input path is required to merge libraries.")

    if len(inputs) == 1:
        return io_formats.read_tracks(inputs[0])

    merged_tracks = [copy.deepcopy(track) for track in io_formats.read_tracks(inputs[0])]
    merged_by_id: dict[str, list[Track]] = {}
    for track in merged_tracks:
        merged_by_id.setdefault(track.spotify_id, []).append(track)

    for path in inputs[1:]:
        seen_counts: dict[str, int] = {}
        for track in io_formats.read_tracks(path):
            incoming_index = seen_counts.get(track.spotify_id, 0)
            seen_counts[track.spotify_id] = incoming_index + 1
            existing_tracks = merged_by_id.setdefault(track.spotify_id, [])
            if incoming_index < len(existing_tracks):
                _merge_track_metadata(existing_tracks[incoming_index], track)
                continue
            copied = copy.deepcopy(track)
            merged_tracks.append(copied)
            existing_tracks.append(copied)
    return merged_tracks
