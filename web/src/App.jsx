import { useEffect, useState } from "react";
import { api } from "./lib/api";
import TimingTower from "./components/TimingTower";
import TrackMap from "./components/TrackMap";
import StrategyGantt from "./components/StrategyGantt";
import GridBuilder from "./components/GridBuilder";
import GridComparison from "./components/GridComparison";
import StrategyMeter from "./components/StrategyMeter";

const NAV = [
  { id: "race", label: "Race Prediction" },
  { id: "manual", label: "Your Grid vs. Predicted" },
  { id: "strategy", label: "Tyre Strategy" },
];

export default function App() {
  const [tab, setTab] = useState("race");
  const [about, setAbout] = useState(null);

  useEffect(() => {
    api.about().then(setAbout).catch(() => {});
  }, []);

  return (
    <div style={{ maxWidth: 1180, margin: "0 auto", padding: "28px 24px 80px" }}>
      <header style={{ marginBottom: 22 }}>
        <div className="eyebrow">
          <span className="dot" /> F1GRID · LIVE PREDICTION ENGINE
        </div>
        <h1 className="display-title">Race weekend, predicted honestly.</h1>
        {about && !about.is_real_data && (
          <div
            style={{
              marginTop: 10,
              padding: "8px 12px",
              borderRadius: 6,
              background: "rgba(224,165,46,0.12)",
              border: "1px solid rgba(224,165,46,0.35)",
              color: "var(--warn)",
              fontSize: "0.8rem",
              maxWidth: 640,
            }}
          >
            Running on synthetic demo data - no real FastF1 cache on this
            deployment yet. Every number is real math on fake results.
          </div>
        )}
      </header>

      <nav style={{ display: "flex", gap: 8, marginBottom: 24 }}>
        {NAV.map((n) => (
          <button
            key={n.id}
            onClick={() => setTab(n.id)}
            style={{
              background: tab === n.id ? "var(--signal)" : "var(--panel)",
              color: tab === n.id ? "#05070A" : "var(--text)",
              border: "1px solid var(--line)",
              borderRadius: 6,
              padding: "8px 16px",
              fontSize: "0.82rem",
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            {n.label}
          </button>
        ))}
      </nav>

      {tab === "race" && <RaceView />}
      {tab === "manual" && <ManualGridView />}
      {tab === "strategy" && <StrategyView />}
    </div>
  );
}

// ── Race Prediction tab ─────────────────────────────────────────────────
function RaceView() {
  const [races, setRaces] = useState([]);
  const [season, setSeason] = useState(null);
  const [round, setRound] = useState(null);
  const [rain, setRain] = useState(0);
  const [useRealGrid, setUseRealGrid] = useState(false);
  const [prediction, setPrediction] = useState(null);
  const [highlight, setHighlight] = useState(null);

  useEffect(() => {
    api.listRaces().then((rs) => {
      setRaces(rs);
      if (rs.length) {
        const last = rs[rs.length - 1];
        setSeason(last.season);
        setRound(last.round);
      }
    });
  }, []);

  useEffect(() => {
    if (season == null || round == null) return;
    api
      .getPrediction(season, round, { rainProb: rain, useRealGrid })
      .then(setPrediction)
      .catch(() => setPrediction(null));
  }, [season, round, rain, useRealGrid]);

  const seasons = [...new Set(races.map((r) => r.season))].sort((a, b) => b - a);
  const roundsForSeason = races.filter((r) => r.season === season);

  return (
    <div style={{ display: "grid", gridTemplateColumns: "300px 1fr", gap: 20 }}>
      <div className="panel" style={{ padding: 16, alignSelf: "start" }}>
        <div className="eyebrow" style={{ marginBottom: 10 }}>SELECT RACE</div>
        <Select label="Season" value={season} onChange={setSeason}
                options={seasons.map((s) => ({ value: s, label: s }))} />
        <Select
          label="Grand Prix" value={round} onChange={setRound}
          options={roundsForSeason.map((r) => ({ value: r.round, label: r.event }))}
        />

        <div className="eyebrow" style={{ marginTop: 18, marginBottom: 8 }}>SCENARIO</div>
        <label style={{ fontSize: "0.78rem", color: "var(--muted)" }}>
          Rain probability - {rain}%
        </label>
        <input
          type="range" min={0} max={100} step={5} value={rain}
          onChange={(e) => setRain(Number(e.target.value))}
          style={{ width: "100%", marginTop: 6 }}
        />

        <label style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 14, fontSize: "0.8rem" }}>
          <input type="checkbox" checked={useRealGrid} onChange={(e) => setUseRealGrid(e.target.checked)} />
          Use real grid (isolate race model)
        </label>
      </div>

      <div>
        {prediction ? (
          <>
            <StrategyMeter meter={prediction.strategy_meter} />
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 16 }}>
              <TimingTower
                predictions={prediction.predictions}
                highlightDriver={highlight}
                onSelectDriver={setHighlight}
              />
              <TrackMap predictions={prediction.predictions} highlightDriver={highlight} />
            </div>
            <p style={{ color: "var(--muted)", fontSize: "0.78rem" }}>
              {prediction.event} · {prediction.used_real_grid ? "real grid given" : "predicted grid (forecast)"} ·
              rain scenario {Math.round(prediction.rain_prob * 100)}%
            </p>
          </>
        ) : (
          <div className="panel" style={{ padding: 40, textAlign: "center", color: "var(--muted)" }}>
            Loading prediction…
          </div>
        )}
      </div>
    </div>
  );
}

// ── Manual Grid tab ──────────────────────────────────────────────────────
function ManualGridView() {
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const handlePredict = async (rows) => {
    setLoading(true);
    try {
      const res = await api.predictManualGrid(rows);
      setResult(res);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ display: "grid", gridTemplateColumns: "340px 1fr", gap: 20 }}>
      <GridBuilder onPredict={handlePredict} loading={loading} />
      {result ? (
        <GridComparison yourGrid={result.your_grid} predictedFinish={result.predicted_finish} />
      ) : (
        <div className="panel" style={{ padding: 40, textAlign: "center", color: "var(--muted)" }}>
          Build a grid and click predict to see your input next to the model's output.
        </div>
      )}
    </div>
  );
}

// ── Strategy tab ─────────────────────────────────────────────────────────
function StrategyView() {
  const [rain, setRain] = useState(0);
  const [results, setResults] = useState(null);
  const totalLaps = 57;

  const candidates = {
    "1-stop M-H": [["MEDIUM", 26], ["HARD", 31]],
    "2-stop S-M-H": [["SOFT", 14], ["MEDIUM", 22], ["HARD", 21]],
    "Wet: INTER-WET": [["INTER", 20], ["WET", 37]],
  };

  useEffect(() => {
    api
      .compareStrategy({
        base_lap_time: 90.0, total_laps: totalLaps, rain_prob: rain / 100,
        sc_lambda: 0.6, strategies: candidates,
      })
      .then(setResults);
  }, [rain]);

  return (
    <div>
      <div className="panel" style={{ padding: 16, marginBottom: 16, maxWidth: 400 }}>
        <label style={{ fontSize: "0.78rem", color: "var(--muted)" }}>
          Rain probability - {rain}%
        </label>
        <input
          type="range" min={0} max={100} step={5} value={rain}
          onChange={(e) => setRain(Number(e.target.value))}
          style={{ width: "100%", marginTop: 6 }}
        />
      </div>
      <StrategyGantt results={results} totalLaps={totalLaps} />
    </div>
  );
}

function Select({ label, value, onChange, options }) {
  return (
    <div style={{ marginBottom: 10 }}>
      <label style={{ fontSize: "0.75rem", color: "var(--muted)", display: "block", marginBottom: 4 }}>
        {label}
      </label>
      <select
        value={value ?? ""}
        onChange={(e) => onChange(Number(e.target.value) || e.target.value)}
        style={{
          width: "100%", background: "var(--void)", border: "1px solid var(--line)",
          borderRadius: 6, color: "var(--text)", padding: "7px 8px", fontSize: "0.82rem",
        }}
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    </div>
  );
}
