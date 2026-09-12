from __future__ import annotations

from pathlib import Path

import typer

from . import auth, io_formats, spotify_client
from .actions import create_playlists, match_text_list, merge_playlists, split_playlist
from .analyze import cluster as cluster_mod
from .analyze import dedupe as dedupe_mod
from .analyze import outliers as outliers_mod
from .config import load_settings
from .reccobeats_client import ReccoBeatsClient

app = typer.Typer(add_completion=False, no_args_is_help=True)
auth_app = typer.Typer(help="Spotify authentication.")
analyze_app = typer.Typer(help="Offline analysis over a pulled/enriched dataset.")
act_app = typer.Typer(help="Write actions back to Spotify.")
app.add_typer(auth_app, name="auth")
app.add_typer(analyze_app, name="analyze")
app.add_typer(act_app, name="act")


# ---------------------------------------------------------------- auth ----
@auth_app.command("login")
def auth_login():
    """Run the Spotify OAuth flow now and cache the token."""
    settings = load_settings()
    auth.login(settings)


# ---------------------------------------------------------------- pull ----
@app.command()
def pull(
    output: Path = typer.Option(..., "--output", "-o", help="Output file path."),
    fmt: str | None = typer.Option(
        None, "--format", "-f", help="json|csv|tsv (inferred from --output if omitted)."
    ),
    playlist: str | None = typer.Option(
        None, "--playlist", help="Only pull playlists whose name contains this substring."
    ),
):
    """Pull playlists + track metadata from Spotify into a local file."""
    settings = load_settings()
    spotify = auth.get_spotify_client(settings)
    tracks = spotify_client.pull_library(spotify, playlist_name_filter=playlist)
    io_formats.write_tracks(tracks, output, fmt)
    typer.echo(f"Pulled {len(tracks)} unique tracks -> {output}")


# -------------------------------------------------------------- enrich ----
@app.command()
def enrich(
    input: Path = typer.Option(..., "--input", "-i"),
    output: Path = typer.Option(..., "--output", "-o"),
    fmt: str | None = typer.Option(None, "--format", "-f"),
):
    """Add ReccoBeats audio features to a pulled dataset. Cached — safe to re-run."""
    settings = load_settings()
    tracks = io_formats.read_tracks(input)
    client = ReccoBeatsClient(settings)
    enriched = client.enrich(tracks)
    io_formats.write_tracks(enriched, output, fmt)

    matched = sum(1 for t in enriched if t.feature_source == "reccobeats")
    typer.echo(f"Enriched {matched}/{len(enriched)} tracks -> {output}")


# ------------------------------------------------------------- analyze ----
@analyze_app.command("cluster")
def analyze_cluster(
    input: Path = typer.Option(..., "--input", "-i"),
    output: Path = typer.Option(..., "--output", "-o"),
    fmt: str | None = typer.Option(None, "--format", "-f"),
    algorithm: str = typer.Option("kmeans", help="kmeans|hdbscan"),
    k: str = typer.Option("auto", help="Number of clusters (kmeans only), or 'auto'."),
    genre_weight: float = typer.Option(1.0),
    audio_feature_weight: float = typer.Option(1.0),
    year_weight: float = typer.Option(0.3),
):
    """Cluster tracks by genre/audio-feature/year similarity."""
    tracks = io_formats.read_tracks(input)
    if algorithm == "hdbscan":
        clustered = cluster_mod.cluster_hdbscan(
            tracks, genre_weight=genre_weight,
            audio_feature_weight=audio_feature_weight, year_weight=year_weight,
        )
    else:
        clustered = cluster_mod.cluster_kmeans(
            tracks, k=k, genre_weight=genre_weight,
            audio_feature_weight=audio_feature_weight, year_weight=year_weight,
        )
    io_formats.write_tracks(clustered, output, fmt)
    n_clusters = len({t.cluster_id for t in clustered if t.cluster_id is not None})
    typer.echo(f"Assigned {len(clustered)} tracks to {n_clusters} clusters -> {output}")


@analyze_app.command("outliers")
def analyze_outliers(
    input: Path = typer.Option(..., "--input", "-i"),
    top_n: int = typer.Option(5, help="Top N outliers per playlist."),
):
    """Print the tracks most out-of-place within each playlist."""
    tracks = io_formats.read_tracks(input)
    results = outliers_mod.top_outliers_by_playlist(tracks, top_n=top_n)
    for pid, scored in results.items():
        name = scored[0][0].playlist_names[0] if scored else pid
        typer.echo(f"\n{name}")
        for t, score in scored:
            typer.echo(f"  {score:.3f}  {t.artist} — {t.title}")


@analyze_app.command("dedupe")
def analyze_dedupe(
    input: Path = typer.Option(..., "--input", "-i"),
    output: Path = typer.Option(..., "--output", "-o"),
    track_threshold: float = typer.Option(0.90),
    playlist_threshold: float = typer.Option(0.60),
):
    """Find near-duplicate tracks and overlapping playlists. Writes a JSON report."""
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
def act_create_from_clusters(
    input: Path = typer.Option(..., "--input", "-i"),
    prefix: str = typer.Option("Auto-"),
    skip_noise: bool = typer.Option(True),
    dry_run: bool = typer.Option(False),
):
    """Create one playlist per cluster from `analyze cluster` output."""
    settings = load_settings()
    spotify = auth.get_spotify_client(settings)
    tracks = io_formats.read_tracks(input)
    created = create_playlists.create_from_clusters(
        spotify, tracks, name_prefix=prefix, skip_noise=skip_noise, dry_run=dry_run
    )
    for cluster_id, playlist_id in created.items():
        typer.echo(f"cluster {cluster_id} -> {playlist_id or '(dry-run)'}")


@act_app.command("split")
def act_split(
    input: Path = typer.Option(
        ..., "--input", "-i", help="Clustered dataset from `analyze cluster`."
    ),
    playlist: str = typer.Option(..., help="Name of the source playlist being split."),
    dry_run: bool = typer.Option(False),
):
    """Split a playlist into sub-playlists using existing cluster assignments."""
    settings = load_settings()
    spotify = auth.get_spotify_client(settings)
    tracks = io_formats.read_tracks(input)
    scoped = [t for t in tracks if playlist in t.playlist_names]
    created = split_playlist.split(spotify, playlist, scoped, dry_run=dry_run)
    for cluster_id, playlist_id in created.items():
        typer.echo(f"part {cluster_id} -> {playlist_id or '(dry-run)'}")


@act_app.command("merge")
def act_merge(
    playlists: str = typer.Option(..., help="Comma-separated playlist names to merge."),
    into: str = typer.Option(..., help="Name for the new merged playlist."),
    dry_run: bool = typer.Option(False),
):
    """Merge two or more existing playlists into one new playlist, deduped."""
    settings = load_settings()
    spotify = auth.get_spotify_client(settings)
    names = [p.strip() for p in playlists.split(",")]
    new_id = merge_playlists.merge(spotify, names, into, dry_run=dry_run)
    typer.echo(f"Merged into '{into}' -> {new_id or '(dry-run)'}")


@act_app.command("add-from-list")
def act_add_from_list(
    file: Path = typer.Option(..., help="Plain-text list: title;artist;album per line."),
    playlist: str = typer.Option(..., help="Target playlist name (created if missing)."),
    delimiter: str = typer.Option(";", help="Field delimiter within each line."),
    dry_run: bool = typer.Option(False),
):
    """Match a plain-text song list against Spotify and add hits to a playlist."""
    settings = load_settings()
    spotify = auth.get_spotify_client(settings)
    rows = match_text_list.parse_text_list(file, field_delimiter=delimiter)
    results = match_text_list.match_all(spotify, rows)
    match_text_list.add_matches_to_playlist(spotify, playlist, results, dry_run=dry_run)


if __name__ == "__main__":
    app()
