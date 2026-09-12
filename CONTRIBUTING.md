# Contributing to playlist-forge

Thanks for contributing.

## Development setup

```bash
git clone https://github.com/mwaddell/playlist-forge
cd playlist-forge
pip install -e ".[dev]"
cp .env.example .env
```

Then set `SPOTIFY_CLIENT_ID` in `.env`.

If you are working on clustering with HDBSCAN, install the optional extra:

```bash
pip install -e ".[dev,hdbscan]"
```

## Run checks before opening a PR

Run unit tests:

```bash
pytest
```

Run lint checks:

```bash
ruff check src tests
```

## Notes for changes that touch Spotify actions

Use `--dry-run` first for `playlist-forge act ...` commands so account-changing actions are previewed before execution.
