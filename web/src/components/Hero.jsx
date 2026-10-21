import BackgroundFX from "./BackgroundFX";
import { TEAM_STYLES } from "../lib/drivers";

export default function Hero({ facts }) {
  const beats = facts?.beats2026;
  const stats = [
    { label: "Forecast release", value: "PRE-RACE" },
    beats?.verdict === "YES"
      ? { label: `2026 walk-forward · ${beats.races ?? 14} races`, value: "AHEAD OF BASELINE", sub: `${beats.pipeline} vs ${beats.baseline}` }
      : beats
        ? { label: `2026 walk-forward · ${beats.races ?? 14} races`, value: beats.pipeline, sub: `baseline ${beats.baseline}` }
        : { label: "Training window", value: facts?.trained || "2019–2024", sub: `held out ${facts?.heldOut || "2025"}` },
    { label: "Current championship", value: "22 DRIVERS", sub: "11 teams on the grid" },
  ].filter(Boolean);

  return (
    <header className="hero">
      <BackgroundFX />
      <div className="hero-inner">
        <div className="masthead">
          <a className="brand" href="#top" aria-label="F1Grid home">
            <span className="brand-mark">F</span>
            <span className="brand-name">F1<span>GRID</span></span>
            <span className="brand-divider" />
            <span className="brand-descriptor">RACE INTELLIGENCE</span>
          </a>
          <a className="grid-link" href="https://www.formula1.com/en/drivers" target="_blank" rel="noreferrer">
            2026 DRIVER LINE-UP <span aria-hidden="true">↗</span>
          </a>
        </div>

        <div className="hero-layout" id="top">
          <div className="hero-copy">
            <div className="eyebrow"><span className="dot" /> PREDICTION ENGINE <span className="eyebrow-divider">/</span> RACE WEEKEND</div>
            <h1 className="display-title">Race weekend,<br /><span>predicted.</span></h1>
            <p className="hero-subtitle">
              A walk-forward Formula 1 forecast built from race data. Every pick is published before lights out, then graded against the result.
            </p>
            <dl className="hero-stats">
              {stats.map((item, index) => (
                <div className="hero-stat" key={item.label}>
                  <dt><span className="hero-stat-index">0{index + 1}</span>{item.label}</dt>
                  <dd>{item.value}{item.sub && <span>{item.sub}</span>}</dd>
                </div>
              ))}
            </dl>
          </div>

          <div className="hero-visual" aria-label="2026 Formula 1 team colourway key">
            <div className="hero-visual__orbit" aria-hidden="true" />
            <div className="hero-visual__car"><CarSVG /></div>
            <div className="hero-visual__label"><span>2026 GRID</span><strong>11</strong><small>CONSTRUCTORS</small></div>
            <div className="hero-livery-key">
              {Object.values(TEAM_STYLES).filter((team) => team.name !== "Sauber").map((team) => (
                <span key={team.name} title={team.name} style={{ "--team": team.accent, "--team-deep": team.deep }} />
              ))}
            </div>
            <p className="hero-visual__caption">TEAM COLOURWAYS <span>2026</span></p>
          </div>
        </div>
      </div>
    </header>
  );
}

function CarSVG() {
  return (
    <svg viewBox="0 0 640 220" role="img" aria-label="Original abstract open-wheel race car illustration">
      <defs>
        <linearGradient id="hero-car-body" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#56606d" />
          <stop offset="0.55" stopColor="#d3d8dc" />
          <stop offset="1" stopColor="#343b46" />
        </linearGradient>
        <linearGradient id="hero-car-glow" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#e21b34" stopOpacity="0" />
          <stop offset="0.5" stopColor="#e21b34" stopOpacity="0.9" />
          <stop offset="1" stopColor="#e21b34" stopOpacity="0" />
        </linearGradient>
        <clipPath id="hero-car-clip">
          <path d="M40 150 L120 150 A46 46 0 0 1 212 150 L360 150 A46 46 0 0 1 452 150 L560 150 L560 128 L470 120 L430 96 Q345 70 300 96 L245 118 L150 122 L110 128 Z" />
        </clipPath>
      </defs>
      <path d="M40 150 L120 150 A46 46 0 0 1 212 150 L360 150 A46 46 0 0 1 452 150 L560 150 L560 128 L470 120 L430 96 Q345 70 300 96 L245 118 L150 122 L110 128 Z" fill="url(#hero-car-body)" stroke="#cbd1d7" strokeOpacity=".6" strokeWidth="2" />
      <path d="M30 140h28v18H30zM556 104h10v46h-10z" fill="#171c24" stroke="#d5dbe1" strokeOpacity=".6" strokeWidth="2" />
      <path d="M120 132 L300 108 L470 124" fill="none" stroke="#e21b34" strokeWidth="5" />
      <path d="M300 96 Q320 78 342 92" fill="none" stroke="#e21b34" strokeWidth="4" />
      <g clipPath="url(#hero-car-clip)"><path d="M-40 180 L190 30" stroke="url(#hero-car-glow)" strokeWidth="20" /></g>
      {[166, 406].map((cx) => (
        <g key={cx}>
          <circle cx={cx} cy="150" r="46" fill="#080b10" stroke="#555d68" strokeWidth="5" />
          <circle cx={cx} cy="150" r="12" fill="#171c24" stroke="#aeb6bf" strokeWidth="3" />
        </g>
      ))}
    </svg>
  );
}
