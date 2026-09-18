# Agent Notes

## Development

- Use Poetry and the `src` layout: `poetry install --with dev` and run tools as `poetry run ...`. Include docs dependencies with `poetry install --with dev,docs`; add the optional HDBSCAN dependency with `--extras hdbscan`.
- CI runs Python 3.10, 3.11, and 3.12. Before a PR, run `poetry run ruff check src tests` followed by `poetry run pytest -q`. For documentation changes, also run `poetry run mkdocs build --strict`.
- Run one test with `poetry run pytest tests/test_cluster.py::test_cluster_kmeans_handles_single_track` (replace the path and node id as needed).

## Architecture And Data

- The console entry point is `playlist_forge.cli:app`; command wiring belongs in `src/playlist_forge/cli.py`.
- `Track` in `src/playlist_forge/models.py` is the canonical record shared across pull, enrichment, analysis, and push operations. Keep serialization behavior centralized in `src/playlist_forge/io_formats.py` rather than handling JSON/CSV/TSV in feature or API modules.
- `src/playlist_forge/analyze/` is intentionally offline and must not import `spotipy`; it operates only on local `Track` datasets and is directly unit tested. Spotify API work belongs in `auth.py`, `spotify_client.py`, or `actions/`.
- Track datasets infer format from the path: `.json` is JSON; `.tsv`, `.tab`, and `.txt` are tab-delimited; any other suffix defaults to CSV. List fields use `;` within CSV/TSV.

## Local State And Safety

- Runtime configuration, cache, and OAuth token live outside the repository in `~/.config/playlist-forge/`, or under `$PLAYLIST_FORGE_HOME` when set. Tests should use `tmp_path`/environment overrides and must not depend on a developer's real configuration or credentials.
- Any command that changes Spotify (`playlist-forge push ...`) must be exercised with `--dry-run` first. `push split` treats HDBSCAN cluster `-1` as noise and skips it by default.
- ReccoBeats audio features are third-party approximations because Spotify's per-track audio-features endpoint is unavailable to new apps. Preserve the feature-source/confidence provenance on `Track` when changing enrichment.
