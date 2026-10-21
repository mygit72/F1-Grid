import BackgroundFX from "./BackgroundFX";

export default function Hero({ facts, onOpenDrivers }) {
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
          <button className="grid-link" type="button" onClick={onOpenDrivers}>
            2026 DRIVER LINE-UP <span aria-hidden="true">↓</span>
          </button>
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

          <div className="hero-visual" aria-label="Stylized Ferrari SF-26 in red and white 2026 livery">
            <div className="hero-visual__orbit" aria-hidden="true" />
            <div className="hero-visual__car"><CarSVG /></div>
            <div className="hero-visual__label"><span>SCUDERIA</span><strong>16</strong><small>FERRARI · SF-26</small></div>
            <p className="hero-visual__caption">ROSSO CORSA <span>2026 LIVERY</span></p>
          </div>
        </div>
      </div>
    </header>
  );
}

function CarSVG() {
  return (
    <svg viewBox="0 0 820 300" role="img" aria-label="Original Ferrari-red and white open-wheel race car illustration">
      <defs>
        <linearGradient id="hero-car-red" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#ff313c" />
          <stop offset="0.42" stopColor="#e8002d" />
          <stop offset="1" stopColor="#8e001c" />
        </linearGradient>
        <linearGradient id="hero-car-white" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#ffffff" />
          <stop offset="1" stopColor="#cfd3d8" />
        </linearGradient>
      </defs>
      <ellipse cx="423" cy="263" rx="355" ry="14" fill="#02060b" opacity=".44" />
      <path d="M77 197 L148 193 L188 177 L267 162 L334 139 L369 108 L429 105 L463 139 L507 158 L588 174 L659 181 L737 190 L780 198 L772 210 L692 210 L664 203 L642 204 L535 201 L510 198 L342 198 L306 203 L224 207 L147 208 L111 202 L77 203 Z" fill="#111821" stroke="#66707c" strokeWidth="2" />
      <path d="M66 188 L142 185 L190 168 L266 155 L324 132 L364 101 L427 97 L462 132 L510 151 L589 167 L663 175 L740 183 L781 191 L777 202 L692 202 L663 195 L642 197 L535 194 L510 191 L341 191 L303 197 L224 200 L145 201 L109 195 L66 196 Z" fill="url(#hero-car-red)" stroke="#ff6670" strokeOpacity=".72" strokeWidth="2" />

      {/* 2026 Ferrari red-and-white bodywork, with black carbon aero surfaces. */}
      <path d="M314 136 L359 104 L426 101 L458 135 L498 151 L470 159 L407 149 L356 149 Z" fill="url(#hero-car-white)" />
      <path d="M256 157 L313 140 L353 151 L339 170 L271 177 L226 174 Z" fill="#f4f4f2" />
      <path d="M488 158 L592 174 L663 181 L655 188 L570 184 L514 176 Z" fill="#f7f7f4" />
      <path d="M151 185 L263 158 L283 161 L211 185 Z" fill="#ffb300" opacity=".95" />
      <path d="M370 151 L437 151 L478 163 L551 176" fill="none" stroke="#9d001d" strokeWidth="5" opacity=".9" />
      <path d="M329 171 L425 167 L485 174" fill="none" stroke="#fff" strokeOpacity=".7" strokeWidth="2" />

      {/* Rear wing and front wing */}
      <path d="M47 160 L55 142 L139 142 L144 151 L109 160 Z" fill="#151b23" stroke="#7b8490" strokeWidth="2" />
      <path d="M48 142 L128 142 L136 150 L51 151 Z" fill="#e8002d" />
      <path d="M745 180 L793 184 L800 197 L778 199 L749 195 Z" fill="#161d26" stroke="#8b939c" strokeWidth="2" />
      <path d="M735 197 L800 198 L797 207 L738 206 Z" fill="#f6f7f8" />
      <path d="M107 156 L95 194 M139 154 L149 195 M743 190 L730 203" stroke="#111821" strokeWidth="5" />

      {/* Cockpit and halo */}
      <path d="M366 112 Q386 82 417 93 L447 133 L430 145 L394 137 Z" fill="#090d12" stroke="#aab3bd" strokeWidth="2" />
      <path d="M380 120 Q398 93 431 111 L447 135 M380 120 L423 126" fill="none" stroke="#d8dde2" strokeWidth="5" strokeLinecap="round" />
      <path d="M404 94 L403 81 L409 79 L416 100" fill="#e8edf0" />

      {/* Number roundel and small livery details */}
      <circle cx="522" cy="169" r="18" fill="#ffd43b" stroke="#fff0a5" strokeWidth="2" />
      <text x="522" y="175" fill="#a0001c" fontFamily="Arial, sans-serif" fontSize="18" fontWeight="800" textAnchor="middle">16</text>
      <path d="M283 183 L305 181 M566 190 L614 192" stroke="#fff" strokeWidth="3" strokeLinecap="round" opacity=".8" />
      <text x="450" y="185" fill="#fff" fontFamily="Arial, sans-serif" fontSize="8" fontWeight="700" letterSpacing="1.2">SCUDERIA</text>

      {[215, 615].map((cx) => (
        <g key={cx}>
          <circle cx={cx} cy="205" r="50" fill="#070a0e" stroke="#343b45" strokeWidth="8" />
          <circle cx={cx} cy="205" r="33" fill="#10161e" stroke="#59636f" strokeWidth="3" />
          <circle cx={cx} cy="205" r="13" fill="#e8002d" stroke="#ffd43b" strokeWidth="3" />
          <circle cx={cx} cy="205" r="4" fill="#f4f6f7" />
        </g>
      ))}
    </svg>
  );
}
