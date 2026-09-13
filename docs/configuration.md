# Configuration

## Environment variables

Secrets stay in `.env` or the process environment.

- `SPOTIFY_CLIENT_ID`: required for Spotify OAuth
- `SPOTIFY_REDIRECT_URI`: optional override for the OAuth callback URL
- `RECCOBEATS_API_KEY`: required for `enrich`
- `PLAYLIST_FORGE_HOME`: optional override for the config and cache root

## Config file

The repository ships `config.example.yaml` at the project root.

By default, the app reads `config.yaml` from
`Path.home() / ".config" / "playlist-forge"`, which is typically:

- macOS and Linux: `~/.config/playlist-forge/config.yaml`
- Windows: `%USERPROFILE%\\.config\\playlist-forge\\config.yaml`

Copy `config.example.yaml` there to override non-secret defaults. If
`PLAYLIST_FORGE_HOME` is set, the app reads
`$PLAYLIST_FORGE_HOME/config.yaml` instead.

```yaml
cluster:
  genre_weight: 1.0
  audio_feature_weight: 1.0
  audio_acousticness_weight:
  audio_danceability_weight:
  audio_energy_weight:
  audio_instrumentalness_weight:
  audio_liveness_weight:
  audio_loudness_weight:
  audio_speechiness_weight:
  audio_tempo_weight:
  audio_valence_weight:
  year_weight: 0.3

dedupe:
  title_artist_threshold: 0.90 # same behavior as --track-threshold
  playlist_overlap_threshold: 0.60 # same behavior as --playlist-threshold

reccobeats:
  base_url: https://api.reccobeats.com
  request_delay_seconds: 0.2
```

Leave per-feature `audio_*_weight` values blank to inherit `audio_feature_weight`.

## Cache and state

- Spotify authentication tokens are cached locally after `auth login`.
- Tokens are stored in `token.json` under the active config directory.
- Analyze commands operate on local dataset files and do not call Spotify.
- Write actions call Spotify only after you explicitly run an `act` command.
