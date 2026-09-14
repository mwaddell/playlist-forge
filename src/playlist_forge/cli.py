from __future__ import annotations

import functools
from pathlib import Path
from typing import Annotated

import typer

from . import auth, io_formats, spotify_client
from .actions import create_playlists, match_text_list, merge_playlists, split_playlist
from .analyze import cluster as cluster_mod
from .analyze import dedupe as dedupe_mod
from .analyze import outliers as outliers_mod
from .config import initialize_config, load_settings, set_spotify_client_id
from .errors import PlaylistForgeError
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
app.add_typer(act_app, name="act")

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


def _playlist_name_for_id(track, playlist_id: str) -> str:
    for idx, pid in enumerate(track.playlist_ids):
        if pid == playlist_id and idx < len(track.playlist_names):
            return track.playlist_names[idx]
    return playlist_id


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
def config_init():
    """Create or replace the local config.json file with defaults.

    Returns:
        None.
    """
    config_path = initialize_config()
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
    playlist: str | None = typer.Option(
        None, "--playlist", help="Only pull playlists whose name contains this substring."
    ),
):
    """Pull playlists and tracks from Spotify into a local dataset.

    Args:
        output: Output file path.
        fmt: Optional output format override.
        playlist: Optional playlist name substring filter.

    Returns:
        None.
    """
    settings = load_settings()
    spotify = auth.get_spotify_client(settings)
    tracks = spotify_client.pull_library(spotify, playlist_name_filter=playlist)
    io_formats.write_tracks(tracks, output, fmt)
    typer.echo(f"Pulled {len(tracks)} unique tracks -> {output}")


# -------------------------------------------------------------- enrich ----
@app.command()
@_handle_cli_errors
def enrich(
    input: Path = typer.Option(..., "--input", "-i"),
    output: Path = typer.Option(..., "--output", "-o"),
    fmt: str | None = typer.Option(None, "--format", "-f"),
):
    """Add ReccoBeats audio features to a pulled dataset file.

    Args:
        input: Input pulled dataset path.
        output: Output enriched dataset path.
        fmt: Optional output format override.

    Returns:
        None.
    """
    settings = load_settings()
    tracks = io_formats.read_tracks(input)
    client = ReccoBeatsClient(settings)
    enriched = client.enrich(tracks)
    io_formats.write_tracks(enriched, output, fmt)

    matched = sum(1 for t in enriched if t.feature_source == "reccobeats")
    typer.echo(f"Enriched {matched}/{len(enriched)} tracks -> {output}")


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


# ------------------------------------------------------------- analyze ----
@analyze_app.command("cluster")
@_handle_cli_errors
def analyze_cluster(
    input: Path = typer.Option(..., "--input", "-i"),
    output: Path = typer.Option(..., "--output", "-o"),
    fmt: str | None = typer.Option(None, "--format", "-f"),
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
    if algorithm == "hdbscan":
        clustered = cluster_mod.cluster_hdbscan(
            tracks,
            genre_weight=resolved_genre_weight,
            audio_feature_weight=resolved_audio_feature_weight,
            audio_feature_weights=resolved_audio_weight_overrides,
            year_weight=resolved_year_weight,
        )
    else:
        clustered = cluster_mod.cluster_kmeans(
            tracks,
            k=k,
            genre_weight=resolved_genre_weight,
            audio_feature_weight=resolved_audio_feature_weight,
            audio_feature_weights=resolved_audio_weight_overrides,
            year_weight=resolved_year_weight,
        )
    io_formats.write_tracks(clustered, output, fmt)
    n_clusters = len({t.cluster_id for t in clustered if t.cluster_id is not None})
    typer.echo(f"Assigned {len(clustered)} tracks to {n_clusters} clusters -> {output}")


@analyze_app.command("outliers")
@_handle_cli_errors
def analyze_outliers(
    input: Path = typer.Option(..., "--input", "-i"),
    top_n: int = typer.Option(5, help="Top N outliers per playlist."),
):
    """Print the highest outlier tracks for each playlist.

    Args:
        input: Input track dataset path.
        top_n: Number of outliers to print per playlist.

    Returns:
        None.
    """
    tracks = io_formats.read_tracks(input)
    results = outliers_mod.top_outliers_by_playlist(tracks, top_n=top_n)
    for pid, scored in results.items():
        name = _playlist_name_for_id(scored[0][0], pid) if scored else pid
        typer.echo(f"\n{name}")
        for t, score in scored:
            typer.echo(f"  {score:.3f}  {t.artist} — {t.title}")


@analyze_app.command("dedupe")
@_handle_cli_errors
def analyze_dedupe(
    input: Path = typer.Option(..., "--input", "-i"),
    output: Path = typer.Option(..., "--output", "-o"),
    track_threshold: float = typer.Option(0.90),
    playlist_threshold: float = typer.Option(0.60),
):
    """Find duplicate tracks and overlapping playlists, then write a JSON report.

    Args:
        input: Input track dataset path.
        output: Output JSON report path.
        track_threshold: Similarity threshold for duplicate track detection.
        playlist_threshold: Jaccard threshold for playlist overlap detection.

    Returns:
        None.
    """
    import json
    from dataclasses import asdict

    tracks = io_formats.read_tracks(input)
    dup_tracks = dedupe_mod.find_duplicate_tracks(tracks, threshold=track_threshold)
    overlaps = dedupe_mod.find_playlist_overlaps(tracks, threshold=playlist_threshold)

    report = {
        "duplicate_tracks": [asdict(d) for d in dup_tracks],
        "playlist_overlaps": [asdict(o) for o in overlaps],
    }
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    typer.echo(
        f"Found {len(dup_tracks)} duplicate track pairs and "
        f"{len(overlaps)} overlapping playlist pairs -> {output}"
    )


# ----------------------------------------------------------------- act ----
@act_app.command("create-from-clusters")
@_handle_cli_errors
def act_create_from_clusters(
    input: Path = typer.Option(..., "--input", "-i"),
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


@act_app.command("split")
@_handle_cli_errors
def act_split(
    input: Path = typer.Option(
        ..., "--input", "-i", help="Clustered dataset from `analyze cluster`."
    ),
    playlist: str = typer.Option(..., help="Name of the source playlist being split."),
    dry_run: bool = typer.Option(False),
):
    """Split one source playlist into cluster-based parts.

    Args:
        input: Clustered input dataset path.
        playlist: Source playlist name to split.
        dry_run: Whether to skip Spotify write operations.

    Returns:
        None.
    """
    settings = load_settings()
    spotify = auth.get_spotify_client(settings)
    tracks = io_formats.read_tracks(input)
    scoped = [t for t in tracks if playlist in t.playlist_names]
    created = split_playlist.split(spotify, playlist, scoped, dry_run=dry_run)
    for cluster_id, playlist_id in created.items():
        typer.echo(f"part {cluster_id} -> {playlist_id or '(dry-run)'}")


@act_app.command("merge")
@_handle_cli_errors
def act_merge(
    playlists: str = typer.Option(..., help="Comma-separated playlist names to merge."),
    into: str = typer.Option(..., help="Name for the new merged playlist."),
    dry_run: bool = typer.Option(False),
):
    """Merge existing playlists into one new deduplicated playlist.

    Args:
        playlists: Comma-separated source playlist names.
        into: Name for the merged playlist.
        dry_run: Whether to skip Spotify write operations.

    Returns:
        None.
    """
    settings = load_settings()
    spotify = auth.get_spotify_client(settings)
    names = [p.strip() for p in playlists.split(",")]
    new_id = merge_playlists.merge(spotify, names, into, dry_run=dry_run)
    typer.echo(f"Merged into '{into}' -> {new_id or '(dry-run)'}")


@act_app.command("add-from-list")
@_handle_cli_errors
def act_add_from_list(
    file: Path = typer.Option(..., help="Plain-text list: title;artist;album per line."),
    playlist: str = typer.Option(..., help="Target playlist name (created if missing)."),
    delimiter: str = typer.Option(";", help="Field delimiter within each line."),
    dry_run: bool = typer.Option(False),
):
    """Match a text list against Spotify and add matched tracks to a playlist.

    Args:
        file: Plain-text input list path.
        playlist: Target playlist name.
        delimiter: Input field delimiter.
        dry_run: Whether to skip Spotify write operations.

    Returns:
        None.
    """
    settings = load_settings()
    spotify = auth.get_spotify_client(settings)
    rows = match_text_list.parse_text_list(file, field_delimiter=delimiter)
    results = match_text_list.match_all(spotify, rows)
    match_text_list.add_matches_to_playlist(spotify, playlist, results, dry_run=dry_run)


if __name__ == "__main__":
    app()
