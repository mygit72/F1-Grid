// Thin fetch wrapper for the F1Grid API. In dev, Vite proxies /api -> :8000
// (see vite.config.js). In production, set VITE_API_BASE to the deployed
// API's URL (e.g. https://your-app.up.railway.app) at build time.
const BASE = import.meta.env.VITE_API_BASE ?? "/api";

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}: ${detail}`);
  }
  return res.json();
}

export const api = {
  about: () => request("/about"),

  listRaces: (season) =>
    request(`/races${season ? `?season=${season}` : ""}`),

  getPrediction: (season, round, { rainProb = 0, useRealGrid = false } = {}) =>
    request(
      `/predictions/${season}/${round}?rain_prob=${rainProb}&use_real_grid=${useRealGrid}`
    ),

  publishPrediction: (season, round, { rainProb = 0, useRealGrid = false } = {}) =>
    request(
      `/predictions/${season}/${round}/publish?rain_prob=${rainProb}&use_real_grid=${useRealGrid}`,
      { method: "POST" }
    ),

  scorePrediction: (season, round) =>
    request(`/predictions/${season}/${round}/score`, { method: "POST" }),

  trackRecord: () => request("/track-record"),

  compareStrategy: (payload) =>
    request("/strategy/compare", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  scenarioDefaults: () => request("/scenario/defaults"),

  scenarioPredict: (season, round, override) =>
    request(`/scenario/predict/${season}/${round}`, {
      method: "POST",
      body: JSON.stringify(override),
    }),

  predictManualGrid: (grid) =>
    request("/predict/manual-grid", {
      method: "POST",
      body: JSON.stringify(grid),
    }),
};
