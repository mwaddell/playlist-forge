# playlist-forge

A command-line tool to export, analyze, and reorganize your Spotify playlists:
find songs that don't belong, playlists that should be merged or split, and
bulk-add new tracks from a plain-text list — all backed by scikit-learn
clustering over your library's genre/audio-feature/year metadata.

Project documentation is published at https://www.waddellnet.com/playlist-forge/

## Important caveat, up front

Spotify deprecated its per-track audio-features endpoint (tempo, energy,
danceability, valence, etc.) for all new API apps in November 2024, and there
is no official replacement. This tool uses **[ReccoBeats](https://reccobeats.com)**,
a third-party API, as a stand-in for that data. Treat audio-feature columns
as approximate, not authoritative — genre (pulled directly from Spotify at
the artist level) is the more reliable signal. Check `reccobeats.com/docs`
for their current request/response shape before relying on this in
production; their API has changed field names before.

## Install

```bash
git clone https://github.com/mwaddell/playlist-forge
cd playlist-forge
poetry install --with dev        # add --extras hdbscan if you want that clusterer
poetry run playlist-forge config init
```

Create a Spotify app at https://developer.spotify.com/dashboard, add
`http://127.0.0.1:8080/callback` as a Redirect URI, then save the Client ID:

```bash
poetry run playlist-forge config clientid YOUR_SPOTIFY_CLIENT_ID
```

No client secret is needed — this uses PKCE.

## Quickstart

```bash
# 1. Authenticate (opens a browser once, caches the token after)
poetry run playlist-forge auth login

# 2. Pull your whole library to a single file
poetry run playlist-forge pull --output library.json

# 3. Enrich with ReccoBeats audio features (default) and/or GetGenre genres
#    (optional — clustering also works on year alone if you skip this)
poetry run playlist-forge enrich --input library.json --output library_features.json
poetry run playlist-forge enrich --input library_features.json --output library_enriched.json --api getgenre

# 4. Convert between dataset formats
poetry run playlist-forge library convert --input library_enriched.json --output library_enriched.tsv

# 5. Cluster everything
poetry run playlist-forge analyze cluster --input library_enriched.json --output clustered.json

# 6. See what looks out of place in each playlist
poetry run playlist-forge analyze outliers --input clustered.json --top-n 5

# 7. Find near-duplicate tracks and overlapping playlists
poetry run playlist-forge analyze dedupe --input library_enriched.json --output dedupe_report.json

# 8. Review clustered.json / dedupe_report.json by hand, then push:
poetry run playlist-forge push split --input clustered.json --dry-run
poetry run playlist-forge push merge --playlists "Chill 1,Chill 2" --into "Chill (merged)" --dry-run
```

**Always run with `--dry-run` first.** Every `push` command supports it and
will print what it would do without touching your account.

## File formats

Every command that reads or writes a track dataset accepts `--format
json|csv|tsv` (or infers input/output formats from file extensions). All
three are lossless round-trips of the same schema — list fields (playlist
names, genres) are `;`-joined in csv/tsv and native arrays in json.

## Architecture

```
pull    (Spotify)      → canonical Track dataset
enrich  (ReccoBeats / GetGenre) → adds audio features or genres where matched
library                → manages local library files
analyze (scikit-learn) → cluster / outliers / dedupe — pure, offline, no API calls
push    (Spotify)      → create new playlists based on analysis
```

`analyze/*` never imports spotipy — it only operates on `Track` objects, so
it's fully unit-tested without needing credentials (see `tests/`). This also
means you can re-run and tune clustering weights repeatedly without re-hitting
any API.

## Config

All configuration lives in `~/.config/playlist-forge/config.json` (or
`$PLAYLIST_FORGE_HOME/config.json` if you override the config root). Create it
with `playlist-forge config init`, reset it with
`playlist-forge config init --force`, then set your Spotify client ID with
`playlist-forge config clientid YOUR_SPOTIFY_CLIENT_ID`, and store GetGenre
credentials with `playlist-forge config getgenres YOUR_GETGENRE_USERNAME`
(the password is prompted securely).
Use
`audio_feature_weight` as the default audio-feature multiplier and
`audio_<feature>_weight` values (for example `audio_tempo_weight`) to override
individual audio features.

## Development

```bash
poetry install --with dev,docs
poetry run pytest
poetry run ruff check src tests
poetry run mkdocs build --strict
```

## License

MIT — see `LICENSE`.
