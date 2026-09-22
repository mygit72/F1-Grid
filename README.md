# F1Grid

[![CI](https://github.com/mygit72/F1-Grid/actions/workflows/ci.yml/badge.svg)](https://github.com/mygit72/F1-Grid/actions/workflows/ci.yml)

## Live demo

- Web app (Vercel): https://f1grid01.vercel.app
- API (Render, FastAPI): https://f1grid-api-ncbj.onrender.com (see `/docs` and `/about`)
- Streamlit app: https://f1-grid-va69eanxsk97khfcuujkfl.streamlit.app

The API and Streamlit app run in deployed mode: read-only endpoints work, and
publish and score are refused. The API is on a free tier that sleeps after
inactivity, so the first request after a while is a cold start and can take up to
about a minute; the web app shows a "waking up the server" message while it wakes.

A Formula 1 prediction engine built around one rule: **a feature describing a
race may only use information available before that race starts.** Every
result in this repo is produced by walk-forward evaluation (train on the past,
predict the next race, never peek at the future) and reported alongside a
grid-order baseline, so any claimed improvement is a real, checkable number —
not a number that's guaranteed by construction.

This exists because it's easy to build an F1 predictor that looks great and
means nothing (train and test on the same information, report the accuracy,
ship it). This repo is the opposite bet: a smaller, more defensible system
where every claim can be traced back to a verifiable evaluation.

## What it does

- **Predicts qualifying, then the race.** A quali model predicts the starting
  grid from pre-qualifying signal only; that predicted grid feeds a race model
  that predicts the full finishing order. Both stages are evaluated separately
  and end-to-end, so you can see exactly how much error each stage adds.
- **Self-checks for leakage.** `features/build.py` builds every feature from
  strictly prior races. `assert_no_leakage()` independently verifies this by
  reversing each race's result and confirming the feature matrix doesn't
  change.
- **Publishes a verifiable track record.** Predictions are written to
  immutable, UTC-timestamped JSON files *before* a race happens
  (`store/predictions.py`). After the race, `score/scorer.py` grades the
  stored prediction against the real result and appends to a public,
  cumulative scorecard. Because the file demonstrably predates the result,
  the track record is auditable, not just claimed.
- **Models rain as an explicit scenario, not a forecast.** A manual 0–1 rain
  probability widens outcome variance and tilts probability toward
  wet-skilled drivers (`model/montecarlo.py`). In the tyre strategy
  simulator, each **compound** also has a rain-suitability rating, so slicks
  in heavy rain are penalized severely (not a flat, ranking-irrelevant
  penalty) and wet-appropriate compounds correctly become the fastest choice
  as rain probability rises — see `tests/test_core.py::test_slicks_lose_to_wets_in_heavy_rain`.
- **Predicts from a hand-entered grid, not just historical races.** Type in
  any starting lineup (`Scenario.features_from_grid`, the `/predict/manual-grid`
  API endpoint, or the "Your Grid vs. Predicted" tab in the web app) and see
  the model's predicted finishing order next to exactly what you typed in.
- **Simulates tyre strategy lap by lap.** Choose a compound sequence (e.g.
  Soft → Medium → Hard); pit stops and stint lengths **emerge** from each
  compound's degradation curve and "cliff," they are never declared as
  "1-stop" or "2-stop" (`model/strategy_sim.py`). Stochastic safety cars are
  layered in via Monte Carlo. This explicitly does **not** model
  wheel-to-wheel traffic or overtaking — see Limitations.
- **Exposes a deep, honest 2026 scenario panel.** Per-team (car pace, aero,
  power unit, reliability) and per-driver (pace, qualifying, consistency, wet
  skill, reliability exposure) dials. Every dial **defaults to a value derived
  from real historical results** and can be overridden — depth without
  hidden guesswork (`model/panel.py`, `model/defaults.py`).

<!-- F1GRID:TRACKRECORD:BEGIN -->
## Track record

Generated from the immutable, timestamped prediction store and the
post-race scorecard (the same source as TRACK_RECORD.md). Actual podiums
come from the real FastF1 result once the race has run. Regenerated on
every publish and score; do not edit by hand.

| Race | Predicted podium | Actual podium | Podium hits | Beat baseline | Links |
| --- | --- | --- | --- | --- | --- |
| 2026 R15 Azerbaijan Grand Prix | 🥇 ANT 🥈 RUS 🥉 NOR | pending | pending | pending | [release](https://github.com/mygit72/F1-Grid/releases/tag/pred-2026-R15) [wayback](http://web.archive.org/web/20260922105143/https://raw.githubusercontent.com/mygit72/F1-Grid/main/artifacts/predictions/2026_R15_Azerbaijan_Grand_Prix__2026-09-21T113507Z__74c95ccf0d_77fc5a.json) |

Summary: 0 race(s) graded, 0 podium pick(s) correct across them, baseline beaten in 0 of 0 graded race(s).
<!-- F1GRID:TRACKRECORD:END -->

## Architecture

```
FastF1 (network)
   │
   ▼
data/ingest.py ───────► artifacts/data/race_results.parquet  (real, cached)
   │
   ▼
features/build.py ────► leakage-free feature rows (+ self-check)
   │
   ├──► model/quali_model.py ──► predicted grid ─┐
   │                                              ▼
   └──► model/order_model.py ◄── (grid feature) ─┘ ──► full finishing order
                  │
                  ├──► model/montecarlo.py  (+ rain scenario) ──► win/podium/points %
                  ├──► model/strategy_sim.py (+ tyres.py)      ──► strategy comparison
                  └──► model/panel.py (2026 scenario overrides) ──► adjusted predictions

store/predictions.py ──► immutable timestamped prediction
score/scorer.py       ──► grades vs. real result ──► artifacts/eval/scorecard.csv
train.py              ──► trains both models, runs walk-forward eval, writes MODEL_CARD.md

app/main.py  (Streamlit)  ──► reads the same core, serves a UI on a public URL
api/main.py  (FastAPI)    ──► reads the same core, serves the same logic as a REST API
```

## Quickstart

This needs internet access (for FastF1) to pull real data — run it on your
own machine, not in a sandboxed environment.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

# 1. Pull real race + qualifying data (takes a while the first time; cached after)
python -m f1grid.data.ingest --seasons 2019 2020 2021 2022 2023 2024 2025

# 2. Train both models, run walk-forward eval, generate the model card
python -m f1grid.train

# 3. Read the honest results
cat artifacts/eval/MODEL_CARD.md

# 4. Run the test suite
pytest tests/ -v
```

### Predicting an upcoming race weekend

```python
from f1grid.data.ingest import load_results
from f1grid.features.build import build_features
from f1grid.model.pipeline import TwoStagePipeline
from f1grid.model.montecarlo import monte_carlo_outcomes
from f1grid.store.predictions import save_prediction

results = load_results()
feats = build_features(results)

train = feats[feats["season"] < 2026]          # everything known so far
pipe = TwoStagePipeline().fit(train)

upcoming = feats[(feats["season"] == 2026) & (feats["round"] == 12)]  # your next race's feature rows
order = pipe.predict_weekend(upcoming, use_real_grid=False)            # predicted grid -> race order
outcomes = monte_carlo_outcomes(order, rain_prob=0.2)                   # add a rain scenario

save_prediction(2026, 12, "Example Grand Prix", outcomes,
               data_cutoff="2026 R11", rain_prob=0.2)
```

After the race, score it:

```python
from f1grid.score.scorer import score_race, track_record
score_race(2026, 12, results)        # grades the stored prediction vs. reality
print(track_record())                # cumulative public accuracy
```

### Comparing tyre strategies

```python
from f1grid.model.strategy_sim import compare_strategies, StintPlan

candidates = {
    "1-stop M-H": [StintPlan("MEDIUM", 26), StintPlan("HARD", 31)],
    "2-stop S-M-H": [StintPlan("SOFT", 14), StintPlan("MEDIUM", 22), StintPlan("HARD", 21)],
}
results = compare_strategies(base_lap_time=90.0, total_laps=57,
                             candidate_sequences=candidates, rain_prob=0.0)
```

### The 2026 scenario panel

```python
from f1grid.model.panel import Scenario

scenario = Scenario.from_results(results)         # real-data defaults for every team/driver
scenario.set_team("Red Bull", aero_efficiency=0.92, power_unit=0.88)
scenario.set_driver("VER", wet_skill=0.95)
adjusted_feats = scenario.apply_to_features(upcoming)
```

## Honesty by design — the things that make this defensible

- **No leakage, structurally enforced and self-tested.** Not "we were
  careful" — there's a test (`tests/test_core.py::test_no_leakage_self_check`)
  that independently re-derives the feature matrix under a scrambled label and
  asserts it's unchanged.
- **Always reports a baseline.** Every evaluation compares against
  "predict the starting grid order" — the bar a model has to clear to be worth
  anything. The model card states plainly whether it clears that bar.
- **Walk-forward only, never k-fold.** Random splits leak the future into the
  past for time series; this codebase doesn't do that anywhere.
- **Predictions are immutable and timestamped**, so a published forecast is
  verifiably pre-registered, not adjusted after the fact.
- **Assumptions are separated from learned values.** The 2026 panel's
  aero/power-unit dials default to neutral because they aren't observable
  from results data; anything beyond that is an explicit, named override you
  set yourself — never silently baked into the model.
- **The strategy simulator states what it doesn't model** (no wheel-to-wheel
  traffic, no overtaking difficulty) rather than implying a more complete
  simulation than it is.

## Known limitations

- Tyre degradation curves in `model/tyres.py` are reasonable defaults, not yet
  fit to real FastF1 stint data — `fit_from_stints()` is a documented
  extension point for plugging in real fitted curves.
- The lap-by-lap simulator is clean-air + stochastic safety cars only; it does
  not model traffic, dirty air, or undercut/overcut interactions between
  specific cars.
- Rain is a manual scenario input, not a weather forecast integration.
- The Streamlit app and FastAPI service are both inference-only: they read
  pre-built artifacts and never run FastF1 ingestion themselves (see
  Deployment below for why).

## How to verify

Every public prediction is committed to git BEFORE the race it forecasts, so
anyone can check the timing independently. To verify a prediction yourself:

1. **Find the file.** Public predictions live in `artifacts/predictions/*.json`.
   Each filename encodes the race, the UTC time it was made, its content hash,
   and a random nonce, for example
   `2026_R15_Azerbaijan_Grand_Prix__2026-09-21T113507Z__74c95ccf0d_77fc5a.json`.

2. **Check the content hash.** The `content_hash` field is the first 10 hex
   characters of the SHA-256 of the record with `content_hash` and `nonce`
   removed and keys sorted. Recompute it and confirm it matches:

   ```bash
   python - <<'PY'
   import hashlib, json, sys
   rec = json.load(open("artifacts/predictions/<file>.json", encoding="utf-8"))
   stored = rec.pop("content_hash"); rec.pop("nonce", None); rec.pop("_path", None)
   payload = json.dumps(rec, sort_keys=True, default=str)
   print("stored    :", stored)
   print("recomputed:", hashlib.sha256(payload.encode()).hexdigest()[:10])
   PY
   ```

   A match proves the file has not been altered since it was written. Old
   `schema_version: 2` files (no `quali_start_utc`/`pre_qualifying` fields) and
   newer `schema_version: 3` files both verify with the same procedure, because
   the hash is taken over whatever fields the record actually contained.

3. **Check it predates the race using third-party server timestamps, not the
   commit date.** A git commit's committer date is set by the committer's own
   machine and can be backdated, so **the commit date alone is not proof.** The
   proof is timestamps recorded by servers we do not control. For every
   published prediction, `TRACK_RECORD.md` and the sidecar in
   `artifacts/provenance/<file>.provenance.json` record:

   - a **GitHub Release** (tag `pred-<season>-R<round>`) with the prediction file
     attached and its content hash in the notes. GitHub stamps it server-side;
     read the timestamps with
     `gh api repos/<owner>/<repo>/releases/tags/pred-<season>-R<round> --jq '{created_at,published_at}'`.
     `published_at` is when GitHub actually published the release (note GitHub
     sets a release's `created_at` to the tagged commit's date, so prefer
     `published_at` as the independent server time).
   - a **Wayback Machine snapshot** of the raw prediction-file URL. Confirm it
     with `curl -s 'https://archive.org/wayback/available?url=<raw-url>'`; the
     `timestamp` field is archive.org's server-side record.
   - the repo's **PushEvent** `created_at` from the events API as a supporting,
     short-lived record (`gh api repos/<owner>/<repo>/events`).

   Each of these must fall before the `race_start_utc` in the file. The store
   (`store/predictions.py`) additionally refuses to write a public prediction
   whose `made_at` is not strictly before the authoritative race start, so a
   retroactive prediction can never enter this directory in the first place.

4. **Read the running tally.** `TRACK_RECORD.md` is regenerated from the
   immutable store, the post-race scorecard, and the provenance sidecars
   (`f1grid/reporting.py`), and lists the release and snapshot links for each
   prediction. It is a pure function of those files, so regenerating it without
   new data produces a byte-for-byte identical file.

## Deployment

### Streamlit (live now, free)

The fastest path to a public, phone/PC-accessible URL:

1. Push this repo to GitHub (public or private).
2. Go to [share.streamlit.io](https://share.streamlit.io), sign in with GitHub,
   click "New app," pick this repo, and set the entrypoint to `app/main.py`.
3. Streamlit Cloud installs `requirements.txt` and deploys automatically. Free
   tier, public URL, redeploys on every push to `main`.

**Before deploying real predictions:** run `python -m f1grid.data.ingest` and
`python -m f1grid.train` locally (this needs internet for FastF1; the deploy
target does not), then commit `artifacts/data/race_results.parquet` and
`artifacts/models/*.joblib` so the deployed app serves real predictions instead
of the synthetic-data fallback. The app runs and is fully functional either
way — it just labels the synthetic case loudly so it's never mistaken for a
real result.

To refresh after each race weekend: re-run ingest + train locally, commit the
updated parquet/models, push. Streamlit Cloud redeploys automatically. This
mirrors a real offline-training/online-serving MLOps pattern and is normal for
a free-tier deployment — FastF1 ingestion is too slow/heavy to run on a
schedule for free.

### FastAPI (live now, free)

The same engine, served as a real backend — matching a FastAPI/Docker/CI stack.

**Run locally:**
```bash
uvicorn api.main:app --reload --port 8000
# docs at http://localhost:8000/docs
```

**Deploy free:**
1. Push to GitHub (the included `.github/workflows/ci.yml` runs tests + a
   Docker build on every push).
2. Deploy the container on **[Railway](https://railway.app)** or
   **[Render](https://render.com)** (both have a free tier; point at this
   repo, they detect the `Dockerfile` automatically) or **[Fly.io](https://fly.io)**
   (`fly launch` picks up the Dockerfile, free allowance, doesn't sleep as
   aggressively as the others).
3. Like the Streamlit deploy, commit real `artifacts/data/*.parquet` and
   `artifacts/models/*.joblib` (from running ingest+train locally) before
   deploying, or the API serves clearly-labeled synthetic demo data.
4. Optional frontend: a small static dashboard calling this API, deployed free
   on **Vercel** or **Netlify**.

Both interfaces (Streamlit + FastAPI) read the exact same `f1grid/` core, so
predictions match between them — there's one trustworthy engine underneath,
just two ways to reach it.

### React showcase frontend (web/)

A cinematic, broadcast-style UI on top of the same API — animated timing
tower, generic track map, tyre-strategy Gantt chart, and a manual grid
builder. See `web/README.md` for setup and deployment (free on Vercel or
Netlify, same pattern as the API: needs `VITE_API_BASE` set to your deployed
API URL).

## Roadmap

- ~~FastAPI service exposing predictions/results/standings.~~ Done — `api/`.
- ~~Streamlit dashboard.~~ Done — `app/`.
- A dedicated static frontend calling the API directly (currently the
  Streamlit app is the primary UI; the API is fully usable standalone via
  `/docs` in the meantime).
- Fit real tyre degradation curves from FastF1 stint data.
- Wet-skill defaults derived from historical wet-race overperformance
  (`model/defaults.py` has the hook; needs a wet-race event list per season).

## Legal

Uses only publicly available FastF1/OpenF1 data. No team logos, sponsor marks,
or official F1 branding. Predictions are analysis and entertainment, not
betting advice, and carry no guarantee of accuracy.
