# F1Grid — Web (React showcase)

A race intelligence frontend for the F1Grid API: 2026 driver portraits and
team colorways, an animated timing tower, a stylized track map, tyre-strategy
scenarios, and a manual grid builder that compares your input with the model.

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

- **No F1 footage, team logos, or official broadcast graphics.** Driver
  portraits are remotely loaded from Formula 1's media CDN and linked to the
  official driver directory. Team colorways are used as data labels. The track
  map is an invented generic circuit shape, not any real track's geometry.
- **No broadcast footage or synthetic driver likenesses.** The interface uses
  the licensed Formula 1 profile portraits noted in `ATTRIBUTIONS.md`; all
  other motorsport graphics and motion are built in the project.

## Components

- `TimingTower.jsx` — driver portraits and livery-colored rows reorder with a
  spring animation (Framer Motion `layout`) when predictions change.
- `TrackMap.jsx` — generic SVG circuit with animated position dots.
- `StrategyGantt.jsx` — compound-colored stint bars; stops are shown as a
  consequence of the sequence, never a separate input.
- `GridBuilder.jsx` + `GridComparison.jsx` — type in a hypothetical starting
  grid, see it side-by-side with the model's predicted finish.
