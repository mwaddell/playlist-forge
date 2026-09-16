# Getting started

## Prerequisites

- Python 3.10 or newer
- [Poetry](https://python-poetry.org/)
- A Spotify app configured with the redirect URI
  `http://127.0.0.1:8080/callback`
- A ReccoBeats API key if you want audio-feature enrichment

## Install

```bash
git clone https://github.com/mwaddell/playlist-forge
cd playlist-forge
poetry install
poetry run playlist-forge config init
```

Then set your Spotify client ID:

```bash
poetry run playlist-forge config clientid YOUR_SPOTIFY_CLIENT_ID
```

No Spotify client secret is required because the tool uses PKCE.

## Authenticate

```bash
poetry run playlist-forge auth login
```

This opens a browser once, completes OAuth, and caches the token for later
commands.

## Quickstart

```bash
# Pull your library
poetry run playlist-forge pull --output library.json

# Add ReccoBeats audio features
poetry run playlist-forge enrich --input library.json --output library_features.json

# Add GetGenres genres
poetry run playlist-forge enrich --input library_features.json --output library_enriched.json --api getgenre

# Convert between dataset formats
poetry run playlist-forge library convert --input library_enriched.json --output library_enriched.tsv

# Merge multiple library files
poetry run playlist-forge library merge --input library_a.json --input library_b.json --output library_merged.json

# Cluster tracks
poetry run playlist-forge analyze cluster --input library_enriched.json --output clustered.json

# Inspect outliers
poetry run playlist-forge analyze outliers --input clustered.json --top-n 5

# Find duplicate tracks and overlapping playlists
poetry run playlist-forge analyze dedupe --input library_enriched.json --output dedupe_report.json

# Review outputs, then apply actions with dry runs first
poetry run playlist-forge push split --input clustered.json --dry-run
poetry run playlist-forge push merge --playlists "Chill 1,Chill 2" --into "Chill (merged)" --dry-run
```

## File formats

The dataset conversion commands with file output (`pull`, `enrich`, `library convert`,
`library merge`,
and `analyze cluster`) accept `--format json|csv|tsv`, or infer input/output
formats from file extensions. `analyze outliers` prints directly to the
terminal, and `analyze dedupe` writes JSON to the explicit `--output` path that
you provide.

- JSON stores list fields as native arrays.
- CSV and TSV store list fields such as genres and playlist names as `;`-joined
  strings.

All three formats round-trip the same track schema.

All three formats use UTF-8 encoding.
