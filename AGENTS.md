# Agent Notes

## Setup And Verification

- This is a Python `>=3.10` Poetry project using the `src` layout. Install development dependencies with `poetry install --with dev`; add documentation dependencies with `poetry install --with dev,docs` and the optional HDBSCAN backend with `--extras hdbscan`.
- Run project tools through Poetry. CI tests Python 3.10, 3.11, and 3.12 with `poetry run ruff check src tests` and `poetry run pytest -q`.
- Ruff targets Python 3.10, has a 120-character line limit, and enforces only `E`, `F`, `I`, and `UP`. Mypy is a development dependency but is not configured or run in CI.
- Run a focused test as `poetry run pytest tests/test_cluster.py::test_cluster_kmeans_handles_single_track`; run `poetry run mkdocs build --strict` for documentation changes. Use `poetry run mkdocs serve` for local documentation previews.
- Keep tests offline. Use `tmp_path` for datasets and local state, `monkeypatch` for module-level paths/dependencies, and mock API sessions, cache calls, and `time.sleep` at their local collaboration boundary. There is no shared `conftest.py` fixture layer.

## Module Boundaries

- The console entry point is `playlist_forge.cli:app`. Register command groups and CLI wiring in `src/playlist_forge/cli.py`; current groups are `config`, `auth`, `library`, `analyze`, and `push`.
- `Track` and `Playlist` in `src/playlist_forge/models.py` are the canonical domain records. Pipeline stages exchange `list[Track]`, not ad hoc dictionaries or API response objects.
- Keep dataset serialization in `src/playlist_forge/io_formats.py`. Keep cross-file precedence and track merge behavior in `src/playlist_forge/library/merge.py`.
- `src/playlist_forge/analyze/` is offline: it may use NumPy, scikit-learn, and RapidFuzz, but must not import `spotipy`, require credentials, or make network calls. It mutates passed `Track` instances for cluster IDs and standalone outlier scores.
- Confine `spotipy` imports to Spotify OAuth/client/write-action modules: `auth.py`, `spotify_client.py`, and `actions/`. ReccoBeats and GetGenre integrations are separate HTTP clients; do not pull Spotify SDK dependencies into enrichment or analysis.
- Map expected operational/API failures to the `PlaylistForgeError` hierarchy in `errors.py`. `_handle_cli_errors` only renders that hierarchy as `Error: ...` with exit code 1; uncaught `ValueError`, I/O/parsing errors, and optional-dependency `ImportError` remain programmer/data errors unless deliberately normalized.

## Data And Serialization

- `Track.spotify_id`, `title`, `artist`, and `album` are required. Preserve `playlist_ids` and `playlist_names` as parallel ordered lists of equal length; playlist overlap and per-playlist outlier analysis reject mismatched metadata.
- Preserve enrichment provenance: `genre_source`/`genre_match_confidence` for genres and `feature_source`/`feature_match_confidence` for audio features. Audio values are optional and analysis must gracefully handle missing values.
- Dataset formats are inferred from paths: `.json` is JSON; `.tsv`, `.tab`, and `.txt` are tab-delimited; every other suffix is CSV. An explicit `--format` overrides inference.
- JSON serializes all current dataclass fields and list fields as arrays. CSV/TSV serializes dataclass fields in declaration order, writes `None` as blank, formats floats to eight decimal places, and joins list fields with `;`. A literal semicolon within a list element cannot round-trip.
- JSON loading is strict (`Track(**row)`) and rejects unknown fields. CSV/TSV loading ignores unknown columns, and empty scalar values become `None`; add corresponding coercion for every new numeric field in `Track.from_flat_dict`.
- `library merge` takes input files in precedence order. It retains duplicate occurrences within an input, matches later same-ID rows by occurrence position, preserves first non-null scalar metadata, and merges playlist memberships and genres in first-seen order.

## Local State, Caching, And APIs

- Runtime config, cache, and OAuth token live under `$PLAYLIST_FORGE_HOME` or `~/.config/playlist-forge/`: `config.json`, `cache/`, and `token.json`. Path constants are evaluated at import time, so set the environment before import or monkeypatch `CONFIG_DIR`, `CONFIG_PATH`, `CACHE_DIR`, and `TOKEN_PATH` in tests.
- Config writes use mode `0600` and reject a config path that is a symlink or non-regular file. Never rely on a developer's actual credentials, token, cache, or home directory in tests.
- Use the SQLite cache for stable Spotify and enrichment lookups. Cache misses/unmatched enrichment may be negative-cached; transient network/API failures must not be cached.
- Preserve each client’s retry semantics when modifying API calls: retry 429/5xx responses with `Retry-After` when supplied and exponential backoff otherwise, then raise a domain error. GetGenre also retries search 202 responses and reauthenticates after 401.
- `rate_limit.py` is a tested generic helper, but production API clients currently implement their own retry parsing/backoff. Do not assume a client uses that helper without wiring it in explicitly.
- ReccoBeats audio features are third-party approximations because Spotify's per-track audio-features endpoint is unavailable to new apps. Preserve the declared feature provenance fields when changing enrichment.

## Command Semantics And Safety

- Follow the established CLI convention of required `--input/-i` and `--output/-o` `Path` options, optional `--format/-f`, and concise `typer.echo` completion output. Use `PlaylistForgeError` for anticipated user-facing failures.
- `pull` deduplicates output by Spotify track ID and accumulates playlist memberships. It skips unavailable/local/removed tracks that lack a Spotify item ID; `--force` bypasses cached playlist pulls.
- Clustering option precedence is CLI per-feature audio weight, then configured per-feature weight, then general audio-feature weight. Keep `analyze cluster` usable when only a subset of feature categories is present.
- `analyze dedupe` writes a JSON report directly rather than through `io_formats.write_tracks`; create its output parent directory if changing that command to support new paths.
- Every Spotify write must support and be exercised with `--dry-run` first. The Spotify write client must avoid API mutation in dry-run mode and batch track additions at Spotify's 100-track request limit.
- `push split` skips tracks without a cluster ID and skips HDBSCAN noise (`cluster_id == -1`) by default. `push merge` resolves source playlists by exact name and deduplicates by Spotify ID, then by ISRC when present.
