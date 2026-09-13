# playlist-forge

`playlist-forge` helps you export, analyze, and reorganize Spotify playlists
from the command line.

## What it does

- Pull your Spotify library into a local dataset.
- Enrich tracks with ReccoBeats audio-feature metadata.
- Analyze clusters, outliers, and duplicate playlists offline.
- Apply reviewed changes back to Spotify with explicit dry runs.

## Workflow

1. Authenticate with Spotify.
2. Pull playlist data to a local file.
3. Optionally enrich the dataset with audio features.
4. Run offline analysis commands.
5. Review the outputs and apply write actions with `--dry-run` first.

## Quick links

- [Getting started](getting-started.md)
- [Command reference](commands.md)
- [Configuration](configuration.md)
- [Development](development.md)

## Architecture

```text
pull    (Spotify)      → canonical Track dataset
enrich  (ReccoBeats)   → adds audio-feature columns where matched
library                → copies dataset as json/csv/tsv
analyze (scikit-learn) → cluster / outliers / dedupe — pure, offline, no API calls
act     (Spotify)      → create/split/merge playlists, add matched songs
```

The `analyze` commands work on local `Track` data only, so you can iterate on
cluster settings without re-hitting the Spotify APIs.
