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
cp .env.example .env
```

Set `SPOTIFY_CLIENT_ID` in `.env`. No Spotify client secret is required because
the tool uses PKCE.

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
poetry run playlist-forge enrich --input library.json --output library_enriched.json

# Cluster tracks
poetry run playlist-forge analyze cluster --input library_enriched.json --output clustered.json

# Inspect outliers
poetry run playlist-forge analyze outliers --input clustered.json --top-n 5

# Find duplicate tracks and overlapping playlists
poetry run playlist-forge analyze dedupe --input library_enriched.json --output dedupe_report.json

# Review outputs, then apply actions with dry runs first
poetry run playlist-forge act create-from-clusters --input clustered.json --dry-run
poetry run playlist-forge act merge --playlists "Chill 1,Chill 2" --into "Chill (merged)" --dry-run
poetry run playlist-forge act add-from-list --file new_songs.txt --playlist "Discover" --dry-run
```

## File formats

Commands that read or write track datasets accept `--format json|csv|tsv`, or
infer the format from the file extension.

- JSON stores list fields as native arrays.
- CSV and TSV store list fields such as genres and playlist names as `;`-joined
  strings.

All three formats round-trip the same track schema.
