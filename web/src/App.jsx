import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import { api } from "./lib/api";
import { parseModelCardFacts } from "./lib/facts";
import Hero from "./components/Hero";
import PredictionSkeleton from "./components/PredictionSkeleton";
import StrategyMeter from "./components/StrategyMeter";

const Podium = lazy(() => import("./components/Podium"));
const TimingTower = lazy(() => import("./components/TimingTower"));
const TrackMap = lazy(() => import("./components/TrackMap"));
const StrategyGantt = lazy(() => import("./components/StrategyGantt"));
const GridBuilder = lazy(() => import("./components/GridBuilder"));
const GridComparison = lazy(() => import("./components/GridComparison"));

const Fallback = () => <div className="skeleton" style={{ height: 220, borderRadius: 14 }} />;

const NAV = [
  { id: "race", number: "01", label: "Race forecast", note: "PREDICT" },
  { id: "manual", number: "02", label: "Grid lab", note: "COMPARE" },
  { id: "strategy", number: "03", label: "Tyre strategy", note: "SIMULATE" },
];

export default function App() {
  const [tab, setTab] = useState("race");
  const [about, setAbout] = useState(null);
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
        } catch {
          await new Promise((resolve) => setTimeout(resolve, 5000));
        }
      }
      if (!cancelled) setServerStatus("error");
    }
    connect();
    return () => { cancelled = true; clearTimeout(slowTimer); };
  }, []);

  const facts = useMemo(() => parseModelCardFacts(about?.model_card), [about]);
  const currentNav = NAV.find((item) => item.id === tab);

  return (
    <div className="app-shell">
      <Hero facts={facts} />
      <main className="wrap">
        {serverStatus === "connecting" && slow && (
          <div className="banner banner-wake" data-testid="waking-banner">
            <span className="spin-dot" /> Waking up the prediction server. It may take a moment to answer after inactivity.
          </div>
        )}
        {serverStatus === "error" && (
          <div className="banner banner-warn" data-testid="server-error-banner">
            Could not reach the API after several tries. It may still be waking up; reload the page in a moment.
          </div>
        )}
        {about && !about.is_real_data && (
          <div className="banner banner-warn">Running on synthetic demo data. The calculations are live, but the race results are sample data.</div>
        )}

        <section className="workspace-heading" aria-label="F1Grid tools">
          <div className="workspace-heading__copy">
            <div className="eyebrow"><span className="eyebrow-index">{currentNav?.number || "01"}</span> RACE CONTROL</div>
            <h2>{currentNav?.label || "Race forecast"}</h2>
            <p>{tab === "race" ? "Build a race picture from the model's expected finish and driver probabilities." : tab === "manual" ? "Set a hypothetical starting order and compare it with the predicted finish." : "Explore how rain changes tyre choices and race time."}</p>
          </div>
          <nav className="nav-pills" aria-label="Prediction tools" role="tablist">
            {NAV.map((item) => (
              <button key={item.id} type="button" role="tab" aria-selected={tab === item.id} className="nav-tab" onClick={() => setTab(item.id)}>
                <span className="nav-tab__number">{item.number}</span>
                <span className="nav-tab__label">{item.label}</span>
                <span className="nav-tab__note">{item.note}</span>
              </button>
            ))}
          </nav>
        </section>

        {tab === "race" && <RaceView />}
        {tab === "manual" && <ManualGridView />}
        {tab === "strategy" && <StrategyView />}

        <footer className="disclaimer">
          <span className="disclaimer__label">About the model</span>
          Predictions use a leakage-free, walk-forward statistical pipeline, published before each race and graded afterward. The model is for race analysis, not betting advice.
          <a href="https://www.formula1.com/en/drivers" target="_blank" rel="noreferrer">Driver portraits and profiles via Formula 1 ↗</a>
        </footer>
      </main>
    </div>
  );
}

function RaceView() {
  const [races, setRaces] = useState([]);
  const [season, setSeason] = useState(null);
  const [round, setRound] = useState(null);
  const [rain, setRain] = useState(0);
  const [useRealGrid, setUseRealGrid] = useState(false);
  const [prediction, setPrediction] = useState(null);
  const [highlight, setHighlight] = useState(null);

  useEffect(() => {
    api.listRaces().then((items) => {
      setRaces(items);
      if (items.length) {
        const last = items[items.length - 1];
        setSeason(last.season);
        setRound(last.round);
      }
    });
  }, []);

  useEffect(() => {
    if (season == null || round == null) return;
    setPrediction(null);
    api.getPrediction(season, round, { rainProb: rain, useRealGrid })
      .then(setPrediction)
      .catch(() => setPrediction(null));
  }, [season, round, rain, useRealGrid]);

  const seasons = [...new Set(races.map((race) => race.season))].sort((a, b) => b - a);
  const roundsForSeason = races.filter((race) => race.season === season);
  const selectedRace = roundsForSeason.find((race) => race.round === round);
  const changeSeason = (nextSeason) => {
    setSeason(nextSeason);
    const available = races.filter((race) => race.season === nextSeason);
    if (available.length) setRound(available[available.length - 1].round);
  };

  return (
    <div className="race-workspace">
      <div className="race-grid">
        <aside className="panel lab-panel race-controls">
          <div className="controls-heading">
            <div><div className="eyebrow">WEEKEND SETUP</div><h3>Race controls</h3></div>
            <span className="round-token">{round ? `R${String(round).padStart(2, "0")}` : "R—"}</span>
          </div>
          <Select label="Season" value={season} onChange={changeSeason} options={seasons.map((item) => ({ value: item, label: item }))} />
          <Select label="Grand Prix" value={round} onChange={setRound} options={roundsForSeason.map((race) => ({ value: race.round, label: race.event }))} />

          <div className="scenario-control">
            <div className="eyebrow">SCENARIO</div>
            <div className="lab-slider-head"><span className="lab-label">Rain probability</span><span className="lab-slider-value">{rain}%</span></div>
            <input type="range" min={0} max={100} step={5} value={rain} aria-label="Rain probability percent" onChange={(event) => setRain(Number(event.target.value))} className="lab-range" />
            <div className="lab-range-labels"><span>Dry</span><span>Heavy rain</span></div>
          </div>

          <label className="lab-checkbox"><input type="checkbox" checked={useRealGrid} onChange={(event) => setUseRealGrid(event.target.checked)} /><span className="switch-track" aria-hidden="true" /><span><strong>Use real starting grid</strong><small>Isolate the race model from grid prediction</small></span></label>
          <div className="controls-footnote"><span className="status-dot" /> MODEL CONNECTED <span>{roundsForSeason.length || "—"} ROUNDS</span></div>
        </aside>

        <section className="forecast-column" aria-label="Race prediction">
          <div className="forecast-heading">
            <div>
              <div className="eyebrow"><span className="dot" /> {season || "2026"} SEASON <span className="eyebrow-divider">/</span> ROUND {round || "—"}</div>
              <h2>{prediction?.event || selectedRace?.event || "Loading race forecast"}</h2>
            </div>
            <div className="forecast-heading__state"><span className="status-dot" /> FORECAST READY</div>
          </div>

          {prediction ? (
            <Suspense fallback={<PredictionSkeleton />}>
              <Podium predictions={prediction.predictions} season={prediction.season} />
              <StrategyMeter meter={prediction.strategy_meter} />
              <div className="analysis-heading"><div><span>01</span><div><strong>Race analysis</strong><small>Expected order and probability view</small></div></div><span>{prediction.predictions.length} DRIVERS</span></div>
              <div className="analysis-grid">
                <TimingTower predictions={prediction.predictions} season={prediction.season} highlightDriver={highlight} onSelectDriver={setHighlight} />
                <TrackMap predictions={prediction.predictions} highlightDriver={highlight} />
              </div>
              <p className="prediction-context">{prediction.event} <span>·</span> {prediction.used_real_grid ? "real grid supplied" : "predicted starting grid"} <span>·</span> {Math.round(prediction.rain_prob * 100)}% rain scenario</p>
            </Suspense>
          ) : <PredictionSkeleton />}
        </section>
      </div>
    </div>
  );
}

function ManualGridView() {
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const handlePredict = async (rows) => {
    setLoading(true);
    try {
      setResult(await api.predictManualGrid(rows));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="manual-workspace">
      <div className="manual-grid">
        <Suspense fallback={<Fallback />}>
          <GridBuilder onPredict={handlePredict} loading={loading} />
          {result ? <GridComparison yourGrid={result.your_grid} predictedFinish={result.predicted_finish} /> : (
            <div className="panel empty-compare"><span className="empty-compare__mark">02</span><strong>Your grid, against the model</strong><p>Arrange the 2026 roster on the left, then run a prediction to compare your starting order with the forecast.</p><div className="empty-compare__line" /></div>
          )}
        </Suspense>
      </div>
    </div>
  );
}

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
    api.compareStrategy({ base_lap_time: 90.0, total_laps: totalLaps, rain_prob: rain / 100, sc_lambda: 0.6, strategies: candidates }).then(setResults);
  }, [rain]);

  return (
    <div className="strategy-workspace">
      <div className="panel lab-panel strategy-controls">
        <div><div className="eyebrow">WEATHER MODEL</div><h3>Set the conditions</h3><p>Compare how the forecast rain changes the race-time range for each tyre plan.</p></div>
        <div className="lab-slider-head"><span className="lab-label">Rain probability</span><span className="lab-slider-value">{rain}%</span></div>
        <input type="range" min={0} max={100} step={5} value={rain} aria-label="Rain probability percent" onChange={(event) => setRain(Number(event.target.value))} className="lab-range" />
        <div className="lab-range-labels"><span>Dry track</span><span>Wet track</span></div>
      </div>
      {results ? <Suspense fallback={<Fallback />}><StrategyGantt results={results} totalLaps={totalLaps} /></Suspense> : <Fallback />}
    </div>
  );
}

function Select({ label, value, onChange, options }) {
  return (
    <div className="lab-field">
      <label className="lab-label">{label}</label>
      <select value={value ?? ""} aria-label={label} onChange={(event) => onChange(Number(event.target.value) || event.target.value)} className="lab-select">
        {options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
      </select>
    </div>
  );
}
