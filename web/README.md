# F1Grid — Web (React showcase)

A cinematic, broadcast-style frontend for the F1Grid API: an animated timing
tower, a stylized track map, animated tyre-strategy bars, and a manual grid
builder that shows exactly what you typed in next to what the model predicted.

This is a **showcase UI**, not a replacement for the Streamlit app — both read
the same FastAPI backend, so predictions match between them.

## Run locally

You need the API running first (it's what this talks to):

```bash
# from the repo root, in another terminal
uvicorn api.main:app --reload --port 8000
```

Then, from this `web/` folder:

```bash
npm install
npm run dev
```

Opens at `http://localhost:5173`. Vite proxies `/api/*` to `localhost:8000`
(see `vite.config.js`), so no CORS setup is needed locally.

## Build for deployment

```bash
npm run build
```

Outputs static files to `dist/`. Deploy `dist/` to **Vercel** or **Netlify**
(both free). Set the environment variable `VITE_API_BASE` to your deployed
API's URL (e.g. `https://your-api.up.railway.app`) before building, so the
production build calls the real backend instead of the local proxy path:

```bash
VITE_API_BASE=https://your-api.up.railway.app npm run build
```

## What's deliberately NOT here

- **No real F1 footage, team logos, or official broadcast graphics.** The
  track map is an invented generic circuit shape, not any real track's
  geometry — tracing an actual circuit would edge into licensed IP. Team
  colors are approximate and used only as a visual key, not branding.
- **No "Drive to Survive" footage or likenesses.** What's borrowed is the
  *design language* (dark, cinematic, broadcast-graphic typography and
  motion) applied to this project's own real predictions — not any actual
  footage, which can't be reproduced here.

## Components

- `TimingTower.jsx` — the signature element: rows reorder with a spring
  animation (Framer Motion `layout`) when predictions change.
- `TrackMap.jsx` — generic SVG circuit with animated position dots.
- `StrategyGantt.jsx` — compound-colored stint bars; stops are shown as a
  consequence of the sequence, never a separate input.
- `GridBuilder.jsx` + `GridComparison.jsx` — type in a hypothetical starting
  grid, see it side-by-side with the model's predicted finish.
