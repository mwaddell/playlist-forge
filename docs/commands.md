# Command reference

## `auth`

### `playlist-forge auth login`

Authenticate with Spotify and cache a token for later commands.

## `pull`

### `playlist-forge pull`

Export playlists and tracks from Spotify into a local dataset.

Options:

- `--output`, `-o`: output file path
- `--format`, `-f`: `json`, `csv`, or `tsv`
- `--playlist`: only pull playlists whose name contains the given substring

## `enrich`

### `playlist-forge enrich`

Attach ReccoBeats audio features to a pulled dataset.

Options:

- `--input`, `-i`: input dataset path
- `--output`, `-o`: output dataset path
- `--format`, `-f`: output format override

## `analyze`

### `playlist-forge analyze cluster`

Cluster tracks by genre, audio-feature, and year similarity.

Options:

- `--input`, `-i`: input dataset path
- `--output`, `-o`: output clustered dataset path
- `--format`, `-f`: output format override
- `--algorithm`: `kmeans` or `hdbscan`
- `--k`: k-means cluster count or `auto`
- `--genre-weight`: weight applied to genre features
- `--audio-feature-weight`: weight applied to audio features
- `--year-weight`: weight applied to release year features

### `playlist-forge analyze outliers`

Print the highest outlier tracks for each playlist.

Options:

- `--input`, `-i`: input dataset path
- `--top-n`: number of outliers to print per playlist

### `playlist-forge analyze dedupe`

Write a JSON report covering duplicate tracks and overlapping playlists.

Options:

- `--input`, `-i`: input dataset path
- `--output`, `-o`: output JSON report path
- `--track-threshold`: similarity threshold for duplicate-track detection
  (matches `dedupe.title_artist_threshold` in `config.yaml`)
- `--playlist-threshold`: Jaccard threshold for playlist overlap detection
  (matches `dedupe.playlist_overlap_threshold` in `config.yaml`)

## `act`

All write commands support `--dry-run`. Use it before changing Spotify data.

### `playlist-forge act create-from-clusters`

Create playlists from clustered dataset output.

Options:

- `--input`, `-i`: clustered dataset path
- `--prefix`: prefix for generated playlist names
- `--skip-noise`: skip cluster `-1`
- `--dry-run`: print actions without writing to Spotify

### `playlist-forge act split`

Split one existing playlist into cluster-based parts.

Options:

- `--input`, `-i`: clustered dataset path
- `--playlist`: source playlist name
- `--dry-run`: print actions without writing to Spotify

### `playlist-forge act merge`

Merge multiple playlists into one deduplicated playlist.

Options:

- `--playlists`: comma-separated source playlist names
- `--into`: name for the merged playlist
- `--dry-run`: print actions without writing to Spotify

### `playlist-forge act add-from-list`

Match tracks from a plain-text file and add successful matches to a playlist.

Options:

- `--file`: plain-text input file containing `title;artist;album` rows
- `--playlist`: target playlist name
- `--delimiter`: field delimiter used in the input file
- `--dry-run`: print actions without writing to Spotify
