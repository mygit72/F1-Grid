# Deploying F1Grid

This is a preparation guide. It does not deploy anything. The Streamlit app and the
API are inference-only: they read pre-built artifacts and, if those are missing,
fall back to synthetic demo data labelled `is_real_data: false`.

## Artifacts a fresh clone needs to serve REAL data

| file | size | purpose |
|---|---|---|
| `artifacts/data/race_results.parquet` | 24 KB | tidy 2019-2026 race results |
| `artifacts/data/schedule.parquet` | 8 KB | authoritative race + qualifying start times |
| `artifacts/data/tyre_curves.json` | 20 KB | fitted tyre-degradation summary (diagnostic) |
| `artifacts/models/quali_model.joblib` | 860 KB | trained qualifying model |
| `artifacts/models/race_model.joblib` | 852 KB | trained race model |
| `artifacts/eval/MODEL_CARD.md` | 12 KB | model card served at `/about` |
| `artifacts/predictions/*.json` | 8 KB each | public pre-race predictions |

Total is about 1.8 MB, well within GitHub and Streamlit Community Cloud limits.

Derived caches that MUST stay out of git (large, regenerable):
`artifacts/fastf1_cache/` (about 375 MB) and `artifacts/data/laps.parquet` (about
392 KB, the lap-level cache used only to fit tyre curves).

## REQUIRED before any deploy: make the real artifacts trackable

The current `.gitignore` ignores `artifacts/data/*.parquet` and
`artifacts/models/*.joblib`. As written, a fresh clone would NOT contain
`race_results.parquet`, `schedule.parquet`, or either model, so it would silently
serve SYNTHETIC data (`is_real_data: false`). Before deploying, replace the two
broad ignore lines with the lap-cache-only ignore plus explicit exceptions, for
example:

```gitignore
# large derived caches only
artifacts/fastf1_cache/
artifacts/data/laps.parquet
artifacts/data/laps.pkl
artifacts/data/*.pkl
# keep the small serving artifacts tracked:
!artifacts/data/race_results.parquet
!artifacts/data/schedule.parquet
artifacts/models/*.joblib
!artifacts/models/quali_model.joblib
!artifacts/models/race_model.joblib
```

Then `git add -f` the tracked artifacts once and verify with
`git ls-files artifacts/` that the six serving files above are present and the
lap cache and fastf1_cache are not.

## Streamlit Community Cloud (the app)

1. Push the repo (with the artifacts tracked, see above) to a public GitHub repo.
2. On https://share.streamlit.io, New app, pick the repo/branch.
3. Main file path: `app/main.py`.
4. Python version: 3.11 or 3.12. Dependencies: `requirements.txt` (already at repo
   root; no extras needed for inference).
5. No secrets are required for inference. Do not add FastF1 or network calls to the
   app: it reads the committed parquet/models only.
6. After it boots, open the About/model-card view and confirm the real-data badge
   shows real data (the app reports `is_real_data: true` only when the parquet is
   present).

## API on Railway or Render (FastAPI + uvicorn)

The API entrypoint is `api.main:app`; start command:
`uvicorn api.main:app --host 0.0.0.0 --port $PORT`.

Railway:
1. New Project, Deploy from GitHub repo.
2. Railway detects Python; set the start command above (it injects `$PORT`).
3. Install command: `pip install -r requirements.txt`.
4. No env vars needed for inference. Confirm `GET /about` returns
   `is_real_data: true`.

Render:
1. New, Web Service, connect the repo.
2. Runtime: Python 3. Build command: `pip install -r requirements.txt`.
3. Start command: `uvicorn api.main:app --host 0.0.0.0 --port $PORT`.
4. Health check path: `/` (returns a small JSON body).

CORS: `api/main.py` currently sets `allow_origins=["*"]`, which lets any origin
call it. For production, restrict it to your web origin, for example set
`allow_origins=["https://<your-app>.vercel.app"]` (and your custom domain if any).

## Web app on Vercel (Vite/React)

1. Import the repo in Vercel. Root directory: `web/`.
2. Framework preset: Vite. Build command: `npm run build`. Output dir: `dist`.
3. Environment variable: `VITE_API_BASE` = the deployed API base URL, for example
   `https://<your-api>.up.railway.app` or the Render URL. Do NOT leave it unset in
   production: the code defaults to `/api` (a dev-only Vite proxy to
   `http://localhost:8000`) which does not exist on Vercel.
4. Redeploy after setting `VITE_API_BASE`. Then set the API's CORS
   `allow_origins` to the resulting Vercel domain (see above) and redeploy the API.

## Docker (API image)

A `Dockerfile` is provided for the API (copies `artifacts/` in and runs uvicorn on
port 8000). Docker is NOT installed on the current build machine, so the image
build was NOT verified this round. To verify elsewhere:

```
docker build -t f1grid-api .
docker run -p 8000:8000 f1grid-api
# then: curl localhost:8000/about  ->  should show is_real_data: true
```

Note the Dockerfile copies `artifacts/` from the build context, so the real
serving artifacts must exist locally (or be mounted as a volume) at build time.
