# playlist-forge

A command-line tool to export, analyze, and reorganize your Spotify playlists:
find songs that don't belong, playlists that should be merged or split, and
bulk-add new tracks from a plain-text list — all backed by scikit-learn
clustering over your library's genre/audio-feature/year metadata.

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
git clone https://github.com/yourname/playlist-forge
cd playlist-forge
pip install -e ".[dev]"          # add [hdbscan] too if you want that clusterer
cp .env.example .env             # fill in SPOTIFY_CLIENT_ID
```

Create a Spotify app at https://developer.spotify.com/dashboard, add
`http://127.0.0.1:8080/callback` as a Redirect URI, and put the Client ID in
`.env`. No client secret is needed — this uses PKCE.

## Quickstart

```bash
# 1. Authenticate (opens a browser once, caches the token after)
playlist-forge auth login

# 2. Pull your whole library to a single file
playlist-forge pull --output library.json

# 3. Enrich with ReccoBeats audio features (optional — clustering also
#    works on genre + year alone if you skip this)
playlist-forge enrich --input library.json --output library_enriched.json

# 4. Cluster everything
playlist-forge analyze cluster --input library_enriched.json --output clustered.json

# 5. See what looks out of place in each playlist
playlist-forge analyze outliers --input clustered.json --top-n 5

# 6. Find near-duplicate tracks and overlapping playlists
playlist-forge analyze dedupe --input library_enriched.json --output dedupe_report.json

# 7. Review clustered.json / dedupe_report.json by hand, then act:
playlist-forge act create-from-clusters --input clustered.json --dry-run
playlist-forge act merge --playlists "Chill 1,Chill 2" --into "Chill (merged)" --dry-run
playlist-forge act add-from-list --file new_songs.txt --playlist "Discover" --dry-run
```

**Always run with `--dry-run` first.** Every `act` command supports it and
will print what it would do without touching your account.

## File formats

Every command that reads or writes a track dataset accepts `--format
json|csv|tsv` (or infers it from the file extension). All three are
lossless round-trips of the same schema — list fields (playlist names,
genres) are `;`-joined in csv/tsv and native arrays in json.

## Architecture

```
pull    (Spotify)      → canonical Track dataset
enrich  (ReccoBeats)   → adds audio-feature columns where matched
analyze (scikit-learn) → cluster / outliers / dedupe — pure, offline, no API calls
act     (Spotify)      → create/split/merge playlists, add matched songs
```

`analyze/*` never imports spotipy — it only operates on `Track` objects, so
it's fully unit-tested without needing credentials (see `tests/`). This also
means you can re-run and tune clustering weights repeatedly without re-hitting
any API.

## Config

Non-secret defaults (clustering weights, dedupe thresholds) live in
`~/.config/playlist-forge/config.yaml` — copy `config.example.yaml` there to
override. Secrets (`SPOTIFY_CLIENT_ID`, `RECCOBEATS_API_KEY`) come from `.env`
/ environment variables only, never from that file.

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check src tests
```

## License

MIT — see `LICENSE`.
