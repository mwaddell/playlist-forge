# Contributing to playlist-forge

Thanks for contributing.

## Development setup

```bash
git clone https://github.com/mwaddell/playlist-forge
cd playlist-forge
poetry install --with dev
cp .env.example .env
```

Then set `SPOTIFY_CLIENT_ID` in `.env`.

If you are working on clustering with HDBSCAN, install the optional extra:

```bash
poetry install --with dev --extras hdbscan
```

## Run checks before opening a PR

Run unit tests:

```bash
poetry run pytest
```

Run lint checks:

```bash
poetry run ruff check src tests
```

## Notes for changes that touch Spotify actions

Use `--dry-run` first for `playlist-forge act ...` commands so account-changing actions are previewed before execution.
