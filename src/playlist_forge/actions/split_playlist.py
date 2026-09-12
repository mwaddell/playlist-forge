"""Split one oversized playlist into several, using cluster assignments.

Expects tracks to already have `cluster_id` set (i.e. run
`playlist-forge analyze cluster` scoped to this one playlist first).
"""

from __future__ import annotations

from collections import defaultdict

import spotipy

from .. import spotify_client


def split(
    spotify: spotipy.Spotify,
    source_playlist_name: str,
    clustered_tracks: list,
    dry_run: bool = False,
) -> dict[int, str | None]:
    """Split clustered tracks into one playlist per cluster.

    Args:
        spotify: Authenticated Spotify API client.
        source_playlist_name: Source playlist display name.
        clustered_tracks: Tracks with existing ``cluster_id`` values.
        dry_run: Whether to skip API writes and only print actions.

    Returns:
        Mapping of cluster ID to created playlist ID, or None for dry-run entries.
    """
    by_cluster: dict[int, list[str]] = defaultdict(list)
    for t in clustered_tracks:
        if t.cluster_id is None:
            continue
        by_cluster[t.cluster_id].append(t.spotify_id)

    created: dict[int, str | None] = {}
    for cluster_id, track_ids in sorted(by_cluster.items()):
        label = "Misc" if cluster_id == -1 else str(cluster_id)
        name = f"{source_playlist_name} — Part {label}"
        playlist_id = spotify_client.create_playlist(
            spotify, name, track_ids,
            description=f"Split from '{source_playlist_name}' by playlist-forge.",
            dry_run=dry_run,
        )
        created[cluster_id] = playlist_id
    return created
