# Development

## Setup

```bash
poetry install --with dev,docs
```

## Validation

```bash
poetry run pytest
poetry run ruff check src tests
poetry run mkdocs build --strict
```

## Local docs preview

```bash
poetry run mkdocs serve
```

## Project layout

- `src/playlist_forge/`: application code
- `tests/`: unit tests
- `docs/`: documentation source for the GitHub Pages site
- `.github/workflows/`: CI and Pages workflows
