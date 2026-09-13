# Configuration

## Environment variables

Secrets stay in `.env` or the process environment.

- `SPOTIFY_CLIENT_ID`: required for Spotify OAuth
- `RECCOBEATS_API_KEY`: required for `enrich`
- `PLAYLIST_FORGE_HOME`: optional override for the config and cache root

## Config file

By default, copy `config.example.yaml` to
`~/.config/playlist-forge/config.yaml` to override non-secret defaults.
If `PLAYLIST_FORGE_HOME` is set, use `$PLAYLIST_FORGE_HOME/config.yaml`
instead.

```yaml
default_format: json

cluster:
  genre_weight: 1.0
  audio_feature_weight: 1.0
  year_weight: 0.3

dedupe:
  title_artist_threshold: 0.90
  playlist_overlap_threshold: 0.60

reccobeats:
  base_url: https://api.reccobeats.com
  request_delay_seconds: 0.2
```

## Cache and state

- Spotify authentication tokens are cached locally after `auth login`.
- Analyze commands operate on local dataset files and do not call Spotify.
- Write actions call Spotify only after you explicitly run an `act` command.
