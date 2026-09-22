import { useEffect, useMemo, useState } from "react";
import { api } from "./lib/api";
import { parseModelCardFacts } from "./lib/facts";
import BackgroundFX from "./components/BackgroundFX";
import Hero from "./components/Hero";
import Podium from "./components/Podium";
import PredictionSkeleton from "./components/PredictionSkeleton";
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
  // "connecting" until the first API call returns. On a free-tier host the
  // instance sleeps after inactivity, so the first request can take up to a
  // minute (a cold start); we show a clear waking-up banner instead of an
  // error or a blank table, then retry until it answers.
  const [serverStatus, setServerStatus] = useState("connecting");
  const [slow, setSlow] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const slowTimer = setTimeout(() => !cancelled && setSlow(true), 2500);
    async function connect() {
      for (let attempt = 0; attempt < 12 && !cancelled; attempt++) {
        try {
          const info = await api.about();
          if (cancelled) return;
          setAbout(info);
          setServerStatus("ready");
          setSlow(false);
          return;
        } catch (e) {
          await new Promise((r) => setTimeout(r, 5000));
        }
      }
      if (!cancelled) setServerStatus("error");
    }
    connect();
    return () => { cancelled = true; clearTimeout(slowTimer); };
  }, []);

  const facts = useMemo(() => parseModelCardFacts(about?.model_card), [about]);

  return (
    <>
      <BackgroundFX />
      <div className="wrap">
        <Hero facts={facts} />

        {serverStatus === "connecting" && slow && (
          <div className="banner banner-wake" data-testid="waking-banner">
            <span className="spin-dot" />
            Waking up the server. The free-tier API sleeps after inactivity, so the
            first request can take up to a minute. Hang tight, retrying...
          </div>
        )}
        {serverStatus === "error" && (
          <div className="banner banner-warn" data-testid="server-error-banner">
            Could not reach the API after several tries. It may still be waking up;
            reload the page in a moment.
          </div>
        )}
        {about && !about.is_real_data && (
          <div className="banner banner-warn">
            Running on synthetic demo data. No real FastF1 cache on this deployment
            yet, so every number is real math on fake results.
          </div>
        )}

        <nav style={{ display: "flex", gap: 8, margin: "22px 0 24px", flexWrap: "wrap" }}>
          {NAV.map((n) => (
            <button key={n.id} className="btn" aria-pressed={tab === n.id} onClick={() => setTab(n.id)}>
              {n.label}
            </button>
          ))}
        </nav>

        {tab === "race" && <RaceView />}
        {tab === "manual" && <ManualGridView />}
        {tab === "strategy" && <StrategyView />}
      </div>
    </>
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
    setPrediction(null);
    api
      .getPrediction(season, round, { rainProb: rain, useRealGrid })
      .then(setPrediction)
      .catch(() => setPrediction(null));
  }, [season, round, rain, useRealGrid]);

  const seasons = [...new Set(races.map((r) => r.season))].sort((a, b) => b - a);
  const roundsForSeason = races.filter((r) => r.season === season);

  return (
    <div className="race-grid" style={{ display: "grid", gridTemplateColumns: "300px 1fr", gap: 20 }}>
      <div className="panel glass" style={{ padding: 16, alignSelf: "start" }}>
        <div className="eyebrow" style={{ marginBottom: 10 }}>SELECT RACE</div>
        <Select label="Season" value={season} onChange={setSeason}
                options={seasons.map((s) => ({ value: s, label: s }))} />
        <Select label="Grand Prix" value={round} onChange={setRound}
                options={roundsForSeason.map((r) => ({ value: r.round, label: r.event }))} />

        <div className="eyebrow" style={{ marginTop: 18, marginBottom: 8 }}>SCENARIO</div>
        <label style={{ fontSize: "0.78rem", color: "var(--muted)" }}>Rain probability {rain}%</label>
        <input type="range" min={0} max={100} step={5} value={rain}
               aria-label="Rain probability percent"
               onChange={(e) => setRain(Number(e.target.value))}
               style={{ width: "100%", marginTop: 6 }} />

        <label style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 14, fontSize: "0.8rem" }}>
          <input type="checkbox" checked={useRealGrid} onChange={(e) => setUseRealGrid(e.target.checked)} />
          Use real grid (isolate race model)
        </label>
      </div>

      <div>
        {prediction ? (
          <>
            <Podium predictions={prediction.predictions} />
            <StrategyMeter meter={prediction.strategy_meter} />
            <div className="race-grid" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 16 }}>
              <TimingTower predictions={prediction.predictions} highlightDriver={highlight} onSelectDriver={setHighlight} />
              <TrackMap predictions={prediction.predictions} highlightDriver={highlight} />
            </div>
            <p style={{ color: "var(--muted)", fontSize: "0.78rem" }}>
              {prediction.event} / {prediction.used_real_grid ? "real grid given" : "predicted grid (forecast)"} /
              rain scenario {Math.round(prediction.rain_prob * 100)}%
            </p>
          </>
        ) : (
          <PredictionSkeleton />
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
    <div className="manual-grid" style={{ display: "grid", gridTemplateColumns: "340px 1fr", gap: 20 }}>
      <GridBuilder onPredict={handlePredict} loading={loading} />
      {result ? (
        <GridComparison yourGrid={result.your_grid} predictedFinish={result.predicted_finish} />
      ) : (
        <div className="panel glass" style={{ padding: 40, textAlign: "center", color: "var(--muted)" }}>
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
    api.compareStrategy({
      base_lap_time: 90.0, total_laps: totalLaps, rain_prob: rain / 100,
      sc_lambda: 0.6, strategies: candidates,
    }).then(setResults);
  }, [rain]);

  return (
    <div>
      <div className="panel glass" style={{ padding: 16, marginBottom: 16, maxWidth: 400 }}>
        <label style={{ fontSize: "0.78rem", color: "var(--muted)" }}>Rain probability {rain}%</label>
        <input type="range" min={0} max={100} step={5} value={rain}
               aria-label="Rain probability percent"
               onChange={(e) => setRain(Number(e.target.value))}
               style={{ width: "100%", marginTop: 6 }} />
      </div>
      {results ? <StrategyGantt results={results} totalLaps={totalLaps} />
               : <div className="skeleton" style={{ height: 220, borderRadius: 12 }} />}
    </div>
  );
}

function Select({ label, value, onChange, options }) {
  return (
    <div style={{ marginBottom: 10 }}>
      <label style={{ fontSize: "0.75rem", color: "var(--muted)", display: "block", marginBottom: 4 }}>{label}</label>
      <select value={value ?? ""} onChange={(e) => onChange(Number(e.target.value) || e.target.value)}
        style={{ width: "100%", background: "var(--void)", border: "1px solid var(--line)",
                 borderRadius: 6, color: "var(--text)", padding: "7px 8px", fontSize: "0.82rem" }}>
        {options.map((o) => (<option key={o.value} value={o.value}>{o.label}</option>))}
      </select>
    </div>
  );
}
