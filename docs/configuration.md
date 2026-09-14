# Configuration

## Config root

- `PLAYLIST_FORGE_HOME`: optional override for the config and cache root

## Config file

Run `playlist-forge config init` to create the default config file, or
`playlist-forge config init --force` to replace it.

By default, the app reads `config.json` from
`Path.home() / ".config" / "playlist-forge"`, which is typically:

- macOS and Linux: `~/.config/playlist-forge/config.json`
- Windows: `%USERPROFILE%\\.config\\playlist-forge\\config.json`

Use `playlist-forge config clientid YOUR_SPOTIFY_CLIENT_ID` to update the
Spotify client ID without editing the file manually. If `PLAYLIST_FORGE_HOME`
is set, the app reads, creates, and updates `$PLAYLIST_FORGE_HOME/config.json`
instead.

Edit `spotify.redirect_uri` in `config.json` if you change the Spotify callback
URL. Edit `reccobeats.api_key` there manually if you need to provide a
ReccoBeats API key.

```json
{
  "spotify": {
    "client_id": null,
    "redirect_uri": "http://127.0.0.1:8080/callback"
  },
  "cluster": {
    "genre_weight": 1.0,
    "audio_feature_weight": 1.0,
    "audio_acousticness_weight": null,
    "audio_danceability_weight": null,
    "audio_energy_weight": null,
    "audio_instrumentalness_weight": null,
    "audio_liveness_weight": null,
    "audio_loudness_weight": null,
    "audio_speechiness_weight": null,
    "audio_tempo_weight": null,
    "audio_valence_weight": null,
    "year_weight": 0.3
  },
  "dedupe": {
    "title_artist_threshold": 0.9,
    "playlist_overlap_threshold": 0.6
  },
  "reccobeats": {
    "api_key": null,
    "base_url": "https://api.reccobeats.com",
    "request_delay_seconds": 0.2
  }
}
```

Leave per-feature `audio_*_weight` values as `null` to inherit `audio_feature_weight`.

## Cache and state

- Spotify authentication tokens are cached locally after `auth login`.
- Tokens are stored in `token.json` under the active config directory.
- Analyze commands operate on local dataset files and do not call Spotify.
- Write actions call Spotify only after you explicitly run an `push` command.
