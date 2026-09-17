from __future__ import annotations

import functools
from dataclasses import replace
from pathlib import Path
from typing import Annotated, Literal

import typer

from . import auth, io_formats, spotify_client
from .actions import create_playlists, merge_playlists
from .analyze import cluster as cluster_mod
from .analyze import dedupe as dedupe_mod
from .analyze import outliers as outliers_mod
from .config import (
    initialize_config,
    load_settings,
    set_getgenre_credentials,
    set_spotify_client_id,
)
from .errors import PlaylistForgeError
from .getgenre_client import GetGenreClient
from .library import merge_libraries, playlist_name_for_id
from .reccobeats_client import ReccoBeatsClient

app = typer.Typer(add_completion=False, no_args_is_help=True)
config_app = typer.Typer(help="Manage local configuration.")
auth_app = typer.Typer(help="Spotify authentication.")
library_app = typer.Typer(help="Manage local library files.")
analyze_app = typer.Typer(help="Offline analysis over a pulled/enriched dataset.")
act_app = typer.Typer(help="Write actions back to Spotify.")
app.add_typer(config_app, name="config")
app.add_typer(auth_app, name="auth")
app.add_typer(library_app, name="library")
app.add_typer(analyze_app, name="analyze")
app.add_typer(act_app, name="push")

_AUDIO_FEATURE_FIELDS = (
    "acousticness",
    "danceability",
    "energy",
    "instrumentalness",
    "liveness",
    "loudness",
    "speechiness",
    "tempo",
    "valence",
)

def _matching_playlist_memberships(track, playlist_filters: list[str] | None) -> tuple[list[str], list[str]]:
    if not playlist_filters:
        return list(track.playlist_ids), list(track.playlist_names)

    matching_ids: list[str] = []
    matching_names: list[str] = []
    for idx, playlist_id in enumerate(track.playlist_ids):
        playlist_name = track.playlist_names[idx] if idx < len(track.playlist_names) else ""
        if spotify_client.playlist_matches_filter(playlist_name, playlist_id, playlist_filters):
            matching_ids.append(playlist_id)
            if idx < len(track.playlist_names):
                matching_names.append(playlist_name)
    return matching_ids, matching_names


def _select_tracks_by_playlist(
    tracks: list,
    playlist_filters: list[str] | None,
    *,
    prune_memberships: bool = False,
) -> list:
    if not playlist_filters:
        return tracks

    selected_tracks: list = []
    for track in tracks:
        matching_ids, matching_names = _matching_playlist_memberships(track, playlist_filters)
        if not matching_ids:
            continue
        if prune_memberships:
            selected_tracks.append(
                replace(track, playlist_ids=matching_ids, playlist_names=matching_names)
            )
        else:
            selected_tracks.append(track)
    return selected_tracks


def _handle_cli_errors(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except PlaylistForgeError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(code=1) from exc

    return wrapper


# -------------------------------------------------------------- config ----
@config_app.command("init")
@_handle_cli_errors
def config_init(
    force: bool = typer.Option(False, "--force", help="Replace an existing config.json file."),
):
    """Create the local config.json file, or replace it with ``--force``.

    Args:
        force: Whether to overwrite an existing config file.

    Returns:
        None.
    """
    config_path = initialize_config(force=force)
    typer.echo(f"Wrote default configuration to {config_path}.")


@config_app.command("clientid")
@_handle_cli_errors
def config_clientid(
    client_id: Annotated[str, typer.Argument(help="Spotify client ID to store in config.json.")],
):
    """Store a Spotify client ID in the local config.json file.

    Args:
        client_id: Spotify client ID value.

    Returns:
        None.
    """
    config_path = set_spotify_client_id(client_id)
    typer.echo(f"Updated Spotify client ID in {config_path}.")


@config_app.command("getgenre")
@_handle_cli_errors
def config_getgenre(
    username: Annotated[str, typer.Argument(help="GetGenre username to store in config.json.")],
):
    """Store GetGenre credentials in the local config.json file.

    Args:
        username: GetGenre username value.

    Returns:
        None.
    """
    password = typer.prompt("GetGenre password", hide_input=True)
    config_path = set_getgenre_credentials(username, password)
    typer.echo(f"Updated GetGenre credentials in {config_path}.")


# ---------------------------------------------------------------- auth ----
@auth_app.command("login")
@_handle_cli_errors
def auth_login():
    """Run Spotify OAuth and cache the token for later commands.

    Returns:
        None.
    """
    settings = load_settings()
    auth.login(settings)


@auth_app.command("logout")
@_handle_cli_errors
def auth_logout():
    """Clear the cached Spotify OAuth token file from disk.

    Returns:
        None.
    """
    removed = auth.logout()
    if removed:
        typer.echo(f"Logged out. Removed cached token at {auth.TOKEN_PATH}.")
    else:
        typer.echo(f"No cached token found at {auth.TOKEN_PATH}.")


# ---------------------------------------------------------------- pull ----
@app.command()
@_handle_cli_errors
def pull(
    output: Path = typer.Option(..., "--output", "-o", help="Output file path."),
    fmt: str | None = typer.Option(
        None, "--format", "-f", help="json|csv|tsv (inferred from --output if omitted)."
    ),
    playlist: Annotated[list[str] | None, typer.Option(
        "--playlist",
        help="Only pull playlists whose name or ID contains any supplied substring.",
    )] = None,
    force: bool = typer.Option(
        False, "--force", help="Pull from Spotify API even if the result was already cached."
    ),
):
    """Pull playlists and tracks from Spotify into a local dataset.

    Args:
        output: Output file path.
        fmt: Optional output format override.
        playlist: Optional playlist name/ID substring filters.

    Returns:
        None.
    """
    settings = load_settings()
    spotify = auth.get_spotify_client(settings)
    tracks = spotify_client.pull_library(spotify, playlist_filters=playlist, force=force)
    io_formats.write_tracks(tracks, output, fmt)
    typer.echo(f"Pulled {len(tracks)} unique tracks -> {output}")


# -------------------------------------------------------------- enrich ----
@app.command()
@_handle_cli_errors
def enrich(
    input: Path = typer.Option(..., "--input", "-i"),
    output: Path = typer.Option(..., "--output", "-o"),
    fmt: str | None = typer.Option(None, "--format", "-f"),
    playlist: Annotated[list[str] | None, typer.Option(
        "--playlist",
        help="Only enrich tracks in playlists whose name or ID contains any supplied substring.",
    )] = None,
    api: Annotated[
        Literal["reccobeats", "getgenre"],
        typer.Option("--api", help="reccobeats|getgenre"),
    ] = "reccobeats",
):
    """Add enrichment data from the selected API to a pulled dataset file.

    Args:
        input: Input pulled dataset path.
        output: Output enriched dataset path.
        fmt: Optional output format override.
        playlist: Optional playlist name/ID substring filters.
        api: Enrichment API to use.

    Returns:
        None.
    """
    settings = load_settings()
    tracks = io_formats.read_tracks(input)
    target_tracks = _select_tracks_by_playlist(tracks, playlist)
    client = ReccoBeatsClient(settings) if api == "reccobeats" else GetGenreClient(settings)
    client.enrich(target_tracks)
    io_formats.write_tracks(tracks, output, fmt)

    matched = (
        sum(1 for t in target_tracks if t.feature_source == "reccobeats")
        if api == "reccobeats"
        else sum(1 for t in target_tracks if t.genre_source and t.genre_source.startswith("getgenre"))
    )
    typer.echo(f"Enriched {matched}/{len(target_tracks)} tracks with {api} -> {output}")


# ---------------------------------------------- library: convert ----
@library_app.command("convert")
@_handle_cli_errors
def library_convert(
    input: Path = typer.Option(..., "--input", "-i"),
    output: Path = typer.Option(..., "--output", "-o"),
    fmt: str | None = typer.Option(None, "--format", "-f"),
):
    """Copy a dataset file into another supported format.

    Args:
        input: Input dataset path.
        output: Output dataset path.
        fmt: Optional output format override.

    Returns:
        None.
    """
    tracks = io_formats.read_tracks(input)
    io_formats.write_tracks(tracks, output, fmt)
    typer.echo(f"Converted {len(tracks)} tracks -> {output}")


@library_app.command("merge")
@_handle_cli_errors
def library_merge(
    input: Annotated[list[Path], typer.Option(..., "--input", "-i")],
    output: Path = typer.Option(..., "--output", "-o"),
    fmt: str | None = typer.Option(None, "--format", "-f"),
):
    """Merge one or more dataset files into a single dataset file.

    Args:
        input: Input dataset paths (repeat ``--input`` for multiple files).
        output: Output dataset path.
        fmt: Optional output format override.

    Returns:
        None.
    """
    tracks = merge_libraries(input)
    io_formats.write_tracks(tracks, output, fmt)
    typer.echo(f"Merged {len(input)} file(s) into {len(tracks)} tracks -> {output}")


# ------------------------------------------------------------- analyze ----
@analyze_app.command("cluster")
@_handle_cli_errors
def analyze_cluster(
    input: Path = typer.Option(..., "--input", "-i"),
    output: Path = typer.Option(..., "--output", "-o"),
    fmt: str | None = typer.Option(None, "--format", "-f"),
    playlist: Annotated[list[str] | None, typer.Option(
        "--playlist",
        help="Only cluster tracks in playlists whose name or ID contains any supplied substring.",
    )] = None,
    algorithm: str = typer.Option("kmeans", help="kmeans|hdbscan"),
    k: str = typer.Option("auto", help="Number of clusters (kmeans only), or 'auto'."),
    genre_weight: Annotated[float | None, typer.Option("--genre-weight")] = None,
    audio_feature_weight: Annotated[float | None, typer.Option("--audio-feature-weight")] = None,
    audio_acousticness_weight: Annotated[
        float | None, typer.Option("--audio-acousticness-weight")
    ] = None,
    audio_danceability_weight: Annotated[
        float | None, typer.Option("--audio-danceability-weight")
    ] = None,
    audio_energy_weight: Annotated[float | None, typer.Option("--audio-energy-weight")] = None,
    audio_instrumentalness_weight: Annotated[
        float | None, typer.Option("--audio-instrumentalness-weight")
    ] = None,
    audio_liveness_weight: Annotated[float | None, typer.Option("--audio-liveness-weight")] = None,
    audio_loudness_weight: Annotated[float | None, typer.Option("--audio-loudness-weight")] = None,
    audio_speechiness_weight: Annotated[
        float | None, typer.Option("--audio-speechiness-weight")
    ] = None,
    audio_tempo_weight: Annotated[float | None, typer.Option("--audio-tempo-weight")] = None,
    audio_valence_weight: Annotated[float | None, typer.Option("--audio-valence-weight")] = None,
    year_weight: Annotated[float | None, typer.Option("--year-weight")] = None,
):
    """Cluster tracks by genre, audio-feature, and year similarity.

    Args:
        input: Input track dataset path.
        output: Output clustered dataset path.
        fmt: Optional output format override.
        playlist: Optional playlist name/ID substring filters.
        algorithm: Clustering algorithm name.
        k: KMeans cluster count or ``auto``.
        genre_weight: Genre feature weight multiplier.
        audio_feature_weight: Default audio feature weight multiplier.
        audio_acousticness_weight: Optional per-feature override for acousticness.
        audio_danceability_weight: Optional per-feature override for danceability.
        audio_energy_weight: Optional per-feature override for energy.
        audio_instrumentalness_weight: Optional per-feature override for instrumentalness.
        audio_liveness_weight: Optional per-feature override for liveness.
        audio_loudness_weight: Optional per-feature override for loudness.
        audio_speechiness_weight: Optional per-feature override for speechiness.
        audio_tempo_weight: Optional per-feature override for tempo.
        audio_valence_weight: Optional per-feature override for valence.
        year_weight: Year feature weight multiplier.

    Returns:
        None.
    """
    if algorithm not in {"kmeans", "hdbscan"}:
        raise PlaylistForgeError(
            f"Unsupported --algorithm '{algorithm}'. Expected one of: kmeans, hdbscan."
        )

    maybe_missing_values = [
        genre_weight,
        audio_feature_weight,
        year_weight,
        audio_acousticness_weight,
        audio_danceability_weight,
        audio_energy_weight,
        audio_instrumentalness_weight,
        audio_liveness_weight,
        audio_loudness_weight,
        audio_speechiness_weight,
        audio_tempo_weight,
        audio_valence_weight,
    ]
    if any(value is None for value in maybe_missing_values):
        settings = load_settings()
        cluster_config = settings.config.get("cluster", {})
    else:
        cluster_config = {}
    resolved_genre_weight = (
        genre_weight if genre_weight is not None else cluster_config.get("genre_weight", 1.0)
    )
    resolved_audio_feature_weight = (
        audio_feature_weight
        if audio_feature_weight is not None
        else cluster_config.get("audio_feature_weight", 1.0)
    )
    resolved_year_weight = (
        year_weight if year_weight is not None else cluster_config.get("year_weight", 0.3)
    )

    cli_audio_weight_overrides = {
        "acousticness": audio_acousticness_weight,
        "danceability": audio_danceability_weight,
        "energy": audio_energy_weight,
        "instrumentalness": audio_instrumentalness_weight,
        "liveness": audio_liveness_weight,
        "loudness": audio_loudness_weight,
        "speechiness": audio_speechiness_weight,
        "tempo": audio_tempo_weight,
        "valence": audio_valence_weight,
    }
    config_audio_weight_overrides = {
        field: cluster_config.get(f"audio_{field}_weight")
        for field in _AUDIO_FEATURE_FIELDS
        if cluster_config.get(f"audio_{field}_weight") is not None
    }
    resolved_audio_weight_overrides = {
        **config_audio_weight_overrides,
        **{field: value for field, value in cli_audio_weight_overrides.items() if value is not None},
    }

    tracks = io_formats.read_tracks(input)
    selected_tracks = _select_tracks_by_playlist(tracks, playlist)
    if playlist:
        selected_track_refs = {id(track) for track in selected_tracks}
        for track in tracks:
            if id(track) not in selected_track_refs:
                track.cluster_id = None
    should_cluster = bool(selected_tracks) or not playlist
    if algorithm == "hdbscan":
        clustered = (
            cluster_mod.cluster_hdbscan(
                selected_tracks,
                genre_weight=resolved_genre_weight,
                audio_feature_weight=resolved_audio_feature_weight,
                audio_feature_weights=resolved_audio_weight_overrides,
                year_weight=resolved_year_weight,
            )
            if should_cluster
            else []
        )
    else:
        clustered = (
            cluster_mod.cluster_kmeans(
                selected_tracks,
                k=k,
                genre_weight=resolved_genre_weight,
                audio_feature_weight=resolved_audio_feature_weight,
                audio_feature_weights=resolved_audio_weight_overrides,
                year_weight=resolved_year_weight,
            )
            if should_cluster
            else []
        )
    io_formats.write_tracks(tracks, output, fmt)
    n_clusters = len({t.cluster_id for t in clustered if t.cluster_id is not None})
    typer.echo(f"Assigned {len(selected_tracks)} tracks to {n_clusters} clusters -> {output}")


@analyze_app.command("outliers")
@_handle_cli_errors
def analyze_outliers(
    input: Path = typer.Option(..., "--input", "-i"),
    playlist: Annotated[list[str] | None, typer.Option(
        "--playlist",
        help="Only analyze playlists whose name or ID contains any supplied substring.",
    )] = None,
    top_n: int = typer.Option(5, help="Top N outliers per playlist."),
):
    """Print the highest outlier tracks for each playlist.

    Args:
        input: Input track dataset path.
        playlist: Optional playlist name/ID substring filters.
        top_n: Number of outliers to print per playlist.

    Returns:
        None.
    """
    tracks = _select_tracks_by_playlist(
        io_formats.read_tracks(input), playlist, prune_memberships=True
    )
    if playlist and not tracks:
        typer.echo("No tracks matched the supplied --playlist filters.")
        return
    results = outliers_mod.top_outliers_by_playlist(tracks, top_n=top_n)
    for pid, scored in results.items():
        name = playlist_name_for_id(scored[0][0], pid) if scored else pid
        typer.echo(f"\n{name}")
        for t, score in scored:
            typer.echo(f"  {score:.3f}  {t.artist} — {t.title}")


@analyze_app.command("dedupe")
@_handle_cli_errors
def analyze_dedupe(
    input: Path = typer.Option(..., "--input", "-i"),
    output: Path = typer.Option(..., "--output", "-o"),
    playlist: Annotated[list[str] | None, typer.Option(
        "--playlist",
        help="Only analyze playlists whose name or ID contains any supplied substring.",
    )] = None,
    track_threshold: float = typer.Option(0.90),
    playlist_threshold: float = typer.Option(0.60),
):
    """Find duplicate tracks and overlapping playlists, then write a JSON report.

    Args:
        input: Input track dataset path.
        output: Output JSON report path.
        playlist: Optional playlist name/ID substring filters.
        track_threshold: Similarity threshold for duplicate track detection.
        playlist_threshold: Jaccard threshold for playlist overlap detection.

    Returns:
        None.
    """
    import json
    from dataclasses import asdict

    tracks = io_formats.read_tracks(input)
    duplicate_scope = _select_tracks_by_playlist(tracks, playlist)
    overlap_scope = _select_tracks_by_playlist(tracks, playlist, prune_memberships=True)
    dup_tracks = dedupe_mod.find_duplicate_tracks(duplicate_scope, threshold=track_threshold)
    overlaps = dedupe_mod.find_playlist_overlaps(overlap_scope, threshold=playlist_threshold)

    report = {
        "duplicate_tracks": [asdict(d) for d in dup_tracks],
        "playlist_overlaps": [asdict(o) for o in overlaps],
    }
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    typer.echo(
        f"Found {len(dup_tracks)} duplicate track pairs and "
        f"{len(overlaps)} overlapping playlist pairs -> {output}"
    )


# ----------------------------------------------------------------- push ----
@act_app.command("split")
@_handle_cli_errors
def act_split(
    input: Path = typer.Option(
        ..., "--input", "-i", help="Clustered dataset from `analyze cluster`."
    ),
    prefix: str = typer.Option("Auto-"),
    skip_noise: bool = typer.Option(True),
    dry_run: bool = typer.Option(False),
):
    """Create Spotify playlists from clustered dataset output.

    Args:
        input: Clustered input dataset path.
        prefix: Prefix for generated playlist names.
        skip_noise: Whether to skip noise cluster ``-1``.
        dry_run: Whether to skip Spotify write operations.

    Returns:
        None.
    """
    settings = load_settings()
    spotify = auth.get_spotify_client(settings)
    tracks = io_formats.read_tracks(input)
    created = create_playlists.create_from_clusters(
        spotify, tracks, name_prefix=prefix, skip_noise=skip_noise, dry_run=dry_run
    )
    for cluster_id, playlist_id in created.items():
        typer.echo(f"cluster {cluster_id} -> {playlist_id or '(dry-run)'}")


@act_app.command("merge")
@_handle_cli_errors
def act_merge(
    playlist: Annotated[list[str] | None, typer.Option(
        "--playlist",
        help="Source playlist name; repeat to merge multiple playlists.",
    )] = None,
    into: str = typer.Option(..., help="Name for the new merged playlist."),
    dry_run: bool = typer.Option(False),
):
    """Merge existing playlists into one new deduplicated playlist.

    Args:
        playlist: Source playlist names to merge.
        into: Name for the merged playlist.
        dry_run: Whether to skip Spotify write operations.

    Returns:
        None.
    """
    settings = load_settings()
    spotify = auth.get_spotify_client(settings)
    new_id = merge_playlists.merge(spotify, playlist or [], into, dry_run=dry_run)
    typer.echo(f"Merged into '{into}' -> {new_id or '(dry-run)'}")


if __name__ == "__main__":
    app()
