# Race weekend routine

The exact, ordered steps to grade a race that has finished and to publish the
next one. A future session with no other context can follow this verbatim.

Two commands do the work:

- `python -m f1grid.publish --score --repo mygit72/F1-Grid` grades every published
  race that now has a real result, appends a "Result" section to that race's GitHub
  Release, regenerates `TRACK_RECORD.md` and the README track record, and commits
  and pushes them.
- `python -m f1grid.publish --next --commit-push --repo mygit72/F1-Grid` predicts
  the next upcoming race, writes the immutable pre-race file, commits ONLY that file,
  pushes, then collects third-party provenance (GitHub Release, Wayback snapshot,
  PushEvent), writes the medal-style release notes, regenerates the track record,
  and pushes again.

Everything is generated from the published files and the real result. Nothing is
hand-written and no value is invented. An already-published prediction file and its
release asset are never modified.

## 0. Prerequisites (check once per session)

```bash
# venv on this machine
PY="C:/projects/projects/f1grid/.venv/Scripts/python.exe"

# run from the repo root
cd C:/projects/projects/f1grid/f1grid

# on main, clean working tree
git status                      # expect: On branch main, nothing to commit
git rev-parse --abbrev-ref HEAD # expect: main

# GitHub CLI authenticated as mygit72 (gh is not on PATH; call by full path)
"C:/Program Files/GitHub CLI/gh.exe" auth status
```

The publish/score code finds `gh` at `C:\Program Files\GitHub CLI\gh.exe`
automatically (see `f1grid/provenance.find_gh`).

## 1. Refresh real data (pulls the finished race's classified result)

```bash
$PY -m f1grid.data.ingest        # updates artifacts/data/race_results.parquet + schedule
```

FastF1 has a rate limit (about 500 calls/hour). If ingestion stops with a rate-limit
error, wait for the reset and re-run; the cache is incremental so it resumes.

## 2. Grade the finished race (Azerbaijan, 2026 R15)

```bash
$PY -m f1grid.publish --score --repo mygit72/F1-Grid
```

This grades R15 against the real result, appends the "Result (added after the race,
<UTC>)" section to release `pred-2026-R15` (the prediction block is copied verbatim
and the code asserts it is unchanged; the release asset is never touched), and
regenerates and pushes `TRACK_RECORD.md` + the README track record.

Confirm afterwards:

```bash
# the Result section is on the release, prediction block intact
"C:/Program Files/GitHub CLI/gh.exe" release view pred-2026-R15 --repo mygit72/F1-Grid --json body -q .body

# the scorecard has the row
type artifacts\eval\scorecard.csv

# the README track record now shows the actual podium and hits for R15
git log -1 --stat
```

## 3. Publish the next race (Bahrain, 2026 R16)

```bash
$PY -m f1grid.publish --next --commit-push --repo mygit72/F1-Grid
```

This predicts R16 from only the data available now, writes the immutable pre-race
file, commits ONLY that file, pushes, collects provenance (Release + Wayback +
PushEvent), writes the medal release notes, regenerates the track record, and pushes.

Confirm afterwards:

```bash
# a new release exists with medal notes, created_at before the race start
"C:/Program Files/GitHub CLI/gh.exe" release view pred-2026-R16 --repo mygit72/F1-Grid --json createdAt,publishedAt,url

# the pushed provenance sidecar records a confirmed Wayback snapshot
type artifacts\provenance\*R16*.provenance.json
```

## 4. Confirm the live sites updated

A push to `main` auto-redeploys the API (Render) and the Streamlit app, and triggers
a Vercel rebuild of the web app. After a minute or two:

```bash
# live API serves real data (replace with the real Render URL)
curl -s https://<render-app>.onrender.com/about | grep is_real_data   # expect true

# the README track record on GitHub shows the new/graded race
```

Open the live Vercel site and confirm the timing tower renders the latest race, and
open the Streamlit app and confirm publish is hidden (deployed mode). The first API
request after the free instance has slept is a cold start and can take up to about a
minute; the web app shows a "waking up the server" message during it.

## 5. If a step fails

- Push rejected (remote moved ahead): `git fetch origin` then `git rebase origin/main`
  and re-run the push. Do NOT force-push main; the only sanctioned force-push is the
  one-off history cleanup, not the weekend routine.
- Wayback save failing: the provenance step records the exact error in the sidecar
  (`wayback_error`) and keeps going; the Release and PushEvent timestamps still stand.
  Re-run later with a small script that calls `provenance.wayback_save(raw_url)` once
  archive.org is reachable, then commit the updated sidecar. Never invent a snapshot.
- FastF1 result not available yet: `--score` prints "no result yet, skipping" and
  writes nothing. Wait for the result to land in FastF1 and re-run. Never append a
  result section before the real result exists.
- Release edit/create failing: check `gh auth status`. `gh release create` treats an
  existing tag as success ("already exists" is reused). If `gh release edit` fails,
  re-run step 2 or 3; the routine only edits the release description and never the
  asset, so retries are safe.
- Prediction file refused as retroactive: the store refuses to publish a race that
  has already started. That is intended. Use `--next` before the race, or `--backtest`
  for an explicitly separate, non-public record.

## Round-3 dry-run (what was verified without writing anything public)

- `python -m f1grid.publish --score --repo mygit72/F1-Grid --no-push --dry-run-release`
  grades nothing because Azerbaijan has no real result yet, so no Result section is
  written and nothing is committed or pushed. This is the honest proof that a result
  section never appears before the result exists.
- `python -m f1grid.publish --next --backtest` runs the full prediction path for the
  next race into the gitignored backtest archive (never public), then the backtest
  file is deleted. It proves the prediction path works without publishing.
- The commit + push + release-notes wiring is covered by the test suite with a mocked
  pusher and `dry_run_release=True`, so no real remote or release is touched.
