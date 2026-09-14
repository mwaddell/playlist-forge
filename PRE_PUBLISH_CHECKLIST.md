# Tasks Remaining for v1.0.0 Release

## 1. Consolidate Configuration

- [x] Remove use of ".env" and move all configuration into `config.json`
- [x] Add a "config init" command to create/recreate the `config.json` file
  with default values, so users can easily reset their configuration if they
  break it.
- [x] Add a "config clientid" command to set the Spotify client ID in `config.json`, so users can
  easily update it without editing the file manually.

## 2. Argument Standardization

- [ ] Update the `pull --playlist` argument to support **multiple playlists**
  (e.g. `pull --playlist "My Playlist" --playlist "Other Playlist"`).
  Additionally, it should support substring matching in both **playlist name** and **playlist ID** (e.g.
  `pull --playlist "My Playlist"` or `pull --playlist "37i9dQZF1DXcBWIGoYBM5M"`).
- [ ] Add the `--playlist` argument (which supports multiple playlists and
  name/id matching) to the `enrich` and `analyze` commands, so users can operate on only specific
  playlists instead of the entire library.
    - Note that `analyze cluster` always updates the cluster_id for the entire
      library, so if `--playlist` is specified, then any tracks not in the
      specified playlists should have their cluster_id set to null, and only
      tracks in the specified playlists should be clustered and assigned a
      cluster for tracks in.
    - Note that `enrich` only updates the matching items, but it leaves any
      others untouched, so if `--playlist` is specified, then only tracks in
      the specified playlists should be enriched, and any others should be left
      as-is.
- [ ] Rename the `--playlists` argument in `act merge` to `--from` and allow
  multiple `--from` arguments to specify multiple source playlists to merge
  into the destination playlist INSTEAD of requiring a single comma-separated
  list of playlists.

## 3. Genre API

- [ ] Add an `--api` argument to the `enrich` command which defaults to
  `reccobeats` but can be set to `getgenre` to use the GetGenre API instead.
- [ ] When specifying `getgenre` as the API, the `enrich` command should call
  the GetGenre API for each track and/or artist, and store the returned
  genre(s) in the output file.
    - https://www.getgenre.com/api
    - Rename `artist_genres` as `genres`
    - Add `genre_source` and `genre_match_confidence` to support future
      addition of other APIs.
    - Add a separate cache sqlite file for GetGenre API results, so that the
      cache is not shared with the ReccoBeats API.

## 4. Additional Library Commands

- [ ] Add a `library merge` command to merge multiple library files into a single file.
    - Allow multiple `--input` arguments to specify the input files to merge.
    - Allow an `--output` argument to specify the output file name.
    - Note: for tracks matched in both files, the merged library should contain
      the union of all playlists and genres from both files.  For metadata
      fields, the merged library should prefer non-null values from the first
      input file, then the second, and so on.
    - Note: specifying only a single `--input` file should work identically to `library convert`
- [ ] Add a `library extract` command to extract a subset of the library by playlist and output the extracted library to a new file.
    - Allow multiple `--playlist` arguments to extract multiple playlists.
    - Note: specifying no `--playlist` arguments should extract no playlists, resulting in an empty library file.
- [ ] Add a `library remove` command to remove a subset of the library by playlist and output the remaining library to a new file.
    - Allow multiple `--playlist` arguments to remove multiple playlists.
    - Note: specifying no `--playlist` arguments should extract all playlists, simply copying the file.

## 5. Additional Analysis Commands

- [ ] Add a `analyze stats` command to compute and display basic statistics about the library, such as:
    - Total number of tracks
    - Total number of playlists
    - Total number of artists
    - Number of "fully enriched" tracks
    - All genres
    - Distribution of release years (min/max/average/median)
    - Distribution of all numeric fields (e.g. popularity, tempo, energy, danceability, etc.)
    - Allow specifying one or more `--playlist` arguments to compute statistics for only those playlists.

## 5. Code Quality

- [ ] Increase test coverage on `spotify_client.py` and
      `reccobeats_client.py` using mocked API responses (e.g. `responses` or
      `pytest-mock`), since those currently require live credentials to exercise.
- [ ] Add unit tests to specifically test for embedded commas/tabs/quotes in
      the csv/tsv/json export formats, since those are the most likely to break the
      CLI's ability to read/write files correctly.
- [ ] Update CI to enforce code coverage thresholds (e.g. 80% or 90%) and fail
      the build if coverage drops below that.

## 6. Manual Testing

- [ ] Run the full pipeline against your **real Spotify account**
      end to end at least once, using `--dry-run` on every `act` command first,
      then without it on a **throwaway test playlist** — not your actual library —
      to confirm writes behave as expected before you trust it near real data.
- [ ] Test against an account with **zero playlists** and one with
      a **very large library** (hundreds of playlists / thousands of tracks) if
      you can get access to one — the pagination and rate-limit handling are the
      parts most likely to break under real-world scale that unit tests won't
      catch.
- [ ] Verify the OAuth flow works from a **clean machine/clean
      browser profile** (no cached Spotify login) — the happy path you've been
      testing with is your own already-authenticated browser, which can hide
      first-run bugs.
- [ ] Confirm what happens if someone runs `act` commands
      _before_ `pull`/`enrich` (missing input file, empty dataset) — CLI tools
      get run out of order constantly; check the error messages are
      understandable rather than raw stack traces.
- [ ] Fresh clone into a **new directory** and follow your own
      README's Quickstart section verbatim, as if you'd never seen the code
      before — this catches missing setup steps that muscle memory papers over.

## 7. Release and Distribution

- [ ] Tag as v1.0.0 and create a GitHub Release with notes, so early users have
      a stable point to install against instead of tracking `main`.
- [ ] Create a `CHANGELOG.md` file and document all changes since the last release, 
      following [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) format.
- [ ] Compile a .exe for Windows users (e.g. via `pyinstaller` or `py2exe`) so
      they can run the CLI without installing Python or any dependencies.
- [ ] Compile a macOS .app bundle for users who don't want to install Python or
       dependencies.
- [ ] Compile a Linux AppImage for users who don't want to install Python or
      dependencies.
- [ ] Publish the compiled binaries to GitHub Releases, so users can download
      them without needing to install Python or dependencies.
