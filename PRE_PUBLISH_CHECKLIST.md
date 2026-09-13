# Pre-Publish Checklist — playlist-forge

A working checklist to run through before flipping this repo to public. Each
item is tagged:

- **[Manual]** — needs a human decision or can't be safely delegated
- **[Copilot]** — a good candidate to hand to GitHub Copilot (chat, code review, or
  Copilot coding agent), with a suggested prompt
- **[Both]** — start with Copilot, but verify the result yourself

Work through this roughly top to bottom — secrets and legal come first because
they're the ones that actually hurt you if skipped.

---

## 1. Secrets & credential hygiene

- [x] **[Manual]** Confirm `.env` was never committed. Check the full git
  history, not just the current working tree:
  ```bash
  git log --all --full-history -- .env
  git log --all -p | grep -i "SPOTIFY_CLIENT\|RECCOBEATS_API_KEY"
  ```
  If anything shows up, the key is compromised the moment the repo goes
  public — rotate it (regenerate the Spotify app's client ID/secret) and
  scrub history with `git filter-repo` or BFG before proceeding, don't just
  delete the file in a new commit.
- [x] **[Manual]** Confirm `token.json` / the OAuth cache path was never
  committed (same git-history check as above, path is
  `~/.config/playlist-forge/token.json` by default so it shouldn't be in the
  repo at all, but verify).
- [x] **[Manual]** Double check `.gitignore` actually covers `.env`,
  `*.sqlite3` (the ReccoBeats cache), and any local `data/`/output directories
  you used while testing — open the file and read it, don't assume.
- [x] **[Copilot]** Ask Copilot to scan for hardcoded secrets or
  accidentally-committed personal data:
  > "Review this repo for any hardcoded API keys, tokens, personal Spotify
  > playlist IDs, usernames, or file paths that reference my local machine.
  > List every match with file and line number."
- [x] **[Manual]** Set up **GitHub secret scanning + push protection** (Settings
  → Code security) before making the repo public, not after.

## 2. Legal / ToS / licensing review

- [x] **[Manual]** Re-read Spotify's
  [Developer Terms of Service](https://developer.spotify.com/terms) and
  confirm nothing in the tool violates them (bulk scraping, redistributing
  Spotify content, etc.) — this is a judgment call only you can make for your
  specific use of the API.
- [x] **[Manual]** Re-read ReccoBeats' terms of service. It's a third-party,
  unofficial data source — decide whether you want to state that dependency
  prominently (the README already flags it, but confirm the wording matches
  their current terms) and whether you're comfortable with users depending on
  a service that could change or disappear.
- [x] **[Manual]** Confirm the `LICENSE` file has your real name/entity instead
  of the placeholder, and that you're intentionally choosing MIT (vs.
  Apache-2.0, which adds an explicit patent grant — worth 5 minutes of
  reading if you're unsure which you want).
- [x] **[Manual]** Decide whether you need a `NOTICE` or disclaimer that this
  is an unofficial, community project not affiliated with or endorsed by
  Spotify — common practice for API client tools, reduces confusion for users
  and lowers your risk if Spotify ever objects to the name/branding.

## 3. Testing beyond the existing unit tests

- [ ] **[Manual]** Run the full pipeline against your **real Spotify account**
  end to end at least once, using `--dry-run` on every `act` command first,
  then without it on a **throwaway test playlist** — not your actual library —
  to confirm writes behave as expected before you trust it near real data.
- [ ] **[Manual]** Test against an account with **zero playlists** and one with
  a **very large library** (hundreds of playlists / thousands of tracks) if
  you can get access to one — the pagination and rate-limit handling are the
  parts most likely to break under real-world scale that unit tests won't
  catch.
- [x] **[Copilot]** Ask Copilot to identify untested edge cases in the
  analysis code:
  > "Look at analyze/cluster.py, analyze/outliers.py, and analyze/dedupe.py.
  > What edge cases (empty playlists, single-track playlists, tracks with no
  > genres, all-identical feature vectors, etc.) are not covered by the
  > existing tests in tests/? Write pytest test cases for the gaps."
  Review every generated test before merging — Copilot will sometimes write
  a test that passes by asserting whatever the code currently does, not what
  it should do.
- [x] **[Copilot]** Ask for a review of API failure handling:
  > "Review spotify_client.py and reccobeats_client.py for how they handle
  > API errors: rate limits (429), auth failures (401), and network timeouts.
  > Flag anywhere a failure would crash the CLI instead of failing gracefully
  > or retrying."
- [ ] **[Manual]** Verify the OAuth flow works from a **clean machine/clean
  browser profile** (no cached Spotify login) — the happy path you've been
  testing with is your own already-authenticated browser, which can hide
  first-run bugs.
- [ ] **[Manual]** Confirm what happens if someone runs `act` commands
  *before* `pull`/`enrich` (missing input file, empty dataset) — CLI tools
  get run out of order constantly; check the error messages are
  understandable rather than raw stack traces.

## 4. Code quality pass

- [x] **[Copilot]** Request a general code review:
  > "Review this codebase for bugs, unclear error messages, and any place
  > where a Track object's mutable state could be silently overwritten or
  > shared incorrectly across playlists (see analyze/outliers.py for the
  > pattern I was already careful about — check the rest of the codebase for
  > the same class of issue)."
- [x] **[Copilot]** Ask Copilot to check type hint consistency and add missing
  docstrings:
  > "Add or improve docstrings for any public function in src/playlist_forge/
  > that doesn't already explain its parameters and return value. Don't
  > change behavior, only add documentation."
- [ ] **[Manual]** Read every Copilot-suggested change before committing —
  especially anything touching `spotify_client.py`'s write operations
  (`create_playlist`, `add_tracks`) or the OAuth flow in `auth.py`. Those are
  the places where a subtly wrong suggestion could modify a user's real
  Spotify library.
- [ ] **[Both]** Increase test coverage on `spotify_client.py` and
  `reccobeats_client.py` using mocked API responses (e.g. `responses` or
  `pytest-mock`), since those currently require live credentials to exercise.
  Ask Copilot to scaffold the mocks, then verify they reflect the *actual*
  Spotify/ReccoBeats response shapes (check against current docs, not just
  what Copilot assumes).
- [ ] **[Manual]** Re-run `ruff check` and `pytest` one final time after all
  the above changes, and confirm CI passes on a fresh push, not just locally.

## 5. Repository hygiene / GitHub best practices

- [x] **[Manual]** Add a `CONTRIBUTING.md` — even a short one — covering how
  to set up a dev environment, run tests, and the PR process. Reduces
  low-quality first-time contributions.
- [x] **[Copilot]** Draft it for you as a starting point:
  > "Write a CONTRIBUTING.md for this repo based on the dev setup already
  > described in README.md, including how to run tests and lint checks."
  Then edit it in your own voice — a generic Copilot-drafted CONTRIBUTING.md
  reads as generic.
- [x] **[Manual]** Add a `CODE_OF_CONDUCT.md` (GitHub has a template you can
  add directly from the repo's Community Standards tab) if you expect or want
  external contributors.
- [x] **[Manual]** Add a `SECURITY.md` describing how someone should privately
  report a vulnerability (even just "email me at X" is enough) rather than
  filing a public issue.
- [x] **[Copilot]** Generate GitHub issue templates:
  > "Create .github/ISSUE_TEMPLATE/bug_report.md and feature_request.md for
  > this CLI tool, following GitHub's standard issue template format."
- [x] **[Manual]** Set repository settings before going public: branch
  protection on `main` (require CI to pass, require PR review if you'll have
  collaborators), disable force-push to `main`, and decide whether to allow
  public forks/issues/discussions.
- [x] **[Manual]** Add relevant **topics/tags** to the GitHub repo (e.g.
  `spotify`, `cli`, `music`, `playlist-management`, `python`) so it's
  discoverable, and write a one-line repo description.
- [x] **[Manual]** Double-check the README's placeholder text — repo URL in
  the clone command, `yourname` in the GitHub URL, your actual name in
  `pyproject.toml`'s `authors` field and `LICENSE`.

## 6. Dependency & supply-chain hygiene

- [x] **[Manual]** Pin or at least floor-pin dependency versions in
  `pyproject.toml` deliberately (they're currently `>=`, which is reasonable
  for a library but means a breaking change in `spotipy` or `scikit-learn`
  could silently break the tool for users — decide if you want to cap major
  versions).
- [x] **[Manual]** Enable **Dependabot** (Settings → Code security → Dependabot
  alerts + security updates) so you get notified of vulnerable dependencies
  after publishing.
- [x] **[Copilot]** Ask for a dependency audit:
  > "List every third-party dependency in pyproject.toml and note which ones
  > are runtime-critical vs. dev-only, and whether any have known maintenance
  > concerns (unmaintained, single-maintainer, etc.) as of your knowledge."
  Treat this as a starting point for your own research, not a final answer —
  verify anything concerning independently.

## 7. Rate limiting & abuse consideration

- [ ] **[Manual]** Think through what happens if someone runs this against a
  Spotify account with an unusually large library, or runs multiple commands
  in a tight loop — does the tool respect Spotify's and ReccoBeats' rate
  limits gracefully, or does it hammer the API?
- [x] **[Copilot]** Ask Copilot to check this specifically:
  > "Review spotify_client.py and reccobeats_client.py for rate-limit
  > handling. Does the code respect Retry-After headers on a 429 response? If
  > not, add backoff/retry logic."
- [ ] **[Manual]** Test the above change against real rate limits if you can
  reasonably trigger one (e.g. pulling a very large library), since simulated
  429s in a unit test won't catch every real-world quirk.

## 8. Final pre-publish pass

- [ ] **[Manual]** Fresh clone into a **new directory** and follow your own
  README's Quickstart section verbatim, as if you'd never seen the code
  before — this catches missing setup steps that muscle memory papers over.
- [ ] **[Manual]** Confirm the GitHub Actions CI badge (if you add one) and
  workflow actually run and pass on the public repo, not just in your local
  clone.
- [ ] **[Manual]** Decide on a version tag (`v0.1.0`) and whether to cut a
  GitHub Release with notes, so early users have a stable point to install
  against instead of tracking `main`.
- [ ] **[Manual]** Take one more look through git history for anything
  personal you don't want public — commit messages referencing your specific
  Spotify library, playlist names, debugging notes, etc.

---

## A note on using Copilot for this pass

Copilot is genuinely useful for the mechanical parts of this list — drafting
templates, scanning for obvious patterns, generating test scaffolding — but
every item above that touches **secrets, legal terms, write operations
against a real Spotify account, or repository permissions** should end with
you personally verifying the outcome, not just accepting the suggestion. The
things most likely to bite you after going public (a leaked key, a ToS
violation, a bug that deletes someone's playlist) are exactly the categories
Copilot can't fully evaluate on your behalf.
