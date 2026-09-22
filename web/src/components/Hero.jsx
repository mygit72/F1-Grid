// Hero: an ORIGINAL abstract open-wheel car silhouette drawn as SVG (generic
// shape, no team livery, no sponsor marks, no number, no real driver likeness),
// with animated speed lines and a light sweep. All copy is factual and derived
// from real artifacts (see lib/facts.js): the process, the train/held-out split,
// and the pre-qualifying baseline result.
export default function Hero({ facts }) {
  const beats = facts?.beats2026;
  const chips = [];
  chips.push({ big: "PRE-RACE", small: "published before each race, graded after" });
  if (beats && beats.verdict === "YES") {
    chips.push({
      big: "BEATS",
      small: `the pre-qualifying baseline, 2026 walk-forward (Spearman ${beats.pipeline} vs ${beats.baseline}, ${beats.races ?? 14} races)`,
    });
  } else if (beats) {
    chips.push({
      big: `${beats.pipeline}`,
      small: `pipeline Spearman vs ${beats.baseline} baseline, 2026 walk-forward (${beats.races ?? 14} races)`,
    });
  }
  chips.push({
    big: facts?.trained || "2019 to 2024",
    small: `trained, held out on ${facts?.heldOut || "2025"}`,
  });

  return (
    <header className="hero">
      <div className="eyebrow"><span className="dot" /> F1GRID / LIVE PREDICTION ENGINE</div>

      <div style={{ display: "grid", gridTemplateColumns: "1.1fr 1fr", gap: 20, alignItems: "center" }}
           className="race-grid">
        <div>
          <h1 className="display-title" style={{ fontSize: "var(--step-4)" }}>
            Race weekend,<br />predicted.
          </h1>
          <p style={{ color: "var(--muted)", maxWidth: 520, marginTop: 10, fontSize: "var(--step-0)" }}>
            A leakage-free, walk-forward Formula 1 forecast. Every prediction is
            published before the race and graded against the real result afterward.
          </p>
          <div className="stat-row">
            {chips.map((c, i) => (
              <span className="chip" key={i}>
                <b>{c.big}</b> {c.small}
              </span>
            ))}
          </div>
        </div>

        <div className="hero-art" aria-hidden="true">
          <CarSVG />
        </div>
      </div>
    </header>
  );
}

function CarSVG() {
  return (
    <svg viewBox="0 0 640 220" width="100%" height="100%" role="img" aria-label="Abstract open-wheel race car">
      <defs>
        <linearGradient id="body" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#161d29" />
          <stop offset="1" stopColor="#0b1017" />
        </linearGradient>
        <linearGradient id="sweep" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="transparent" />
          <stop offset="0.5" stopColor="rgba(0,229,199,0.55)" />
          <stop offset="1" stopColor="transparent" />
        </linearGradient>
        <clipPath id="carclip">
          <path d="M40 150 L120 150 A46 46 0 0 1 212 150 L360 150 A46 46 0 0 1 452 150
                   L560 150 L560 128 L470 120 L430 96 Q345 70 300 96 L245 118 L150 122 L110 128 Z" />
        </clipPath>
      </defs>

      {/* speed lines behind the car */}
      {[60, 92, 124, 156].map((y, i) => (
        <rect key={y} className="speed-line" x="0" y={y} width="120" height="3" rx="1.5"
              fill={i % 2 ? "var(--telemetry)" : "var(--signal)"} opacity="0.5"
              style={{ animationDelay: `${i * 0.25}s` }} />
      ))}

      {/* car body silhouette */}
      <path d="M40 150 L120 150 A46 46 0 0 1 212 150 L360 150 A46 46 0 0 1 452 150
               L560 150 L560 128 L470 120 L430 96 Q345 70 300 96 L245 118 L150 122 L110 128 Z"
            fill="url(#body)" stroke="var(--line)" strokeWidth="2" />
      {/* halo + cockpit accent */}
      <path d="M300 96 Q320 78 342 92" fill="none" stroke="var(--telemetry)" strokeWidth="3" opacity="0.9" />
      {/* front + rear wing */}
      <rect x="30" y="140" width="26" height="18" rx="2" fill="#0b1017" stroke="var(--line)" strokeWidth="1.5" />
      <rect x="556" y="104" width="10" height="46" rx="2" fill="#0b1017" stroke="var(--signal)" strokeWidth="1.5" />
      {/* signal accent line along the body */}
      <path d="M120 132 L300 108 L470 124" fill="none" stroke="var(--signal)" strokeWidth="2.5" opacity="0.85" />

      {/* light sweep clipped to the body */}
      <g clipPath="url(#carclip)">
        <rect className="sweep" x="-200" y="60" width="200" height="120" fill="url(#sweep)" />
      </g>

      {/* wheels */}
      {[166, 406].map((cx) => (
        <g key={cx}>
          <circle cx={cx} cy="150" r="46" fill="#0a0e14" stroke="var(--line)" strokeWidth="3" />
          <g className="wheel-spin" style={{ transformOrigin: `${cx}px 150px` }}>
            {[0, 60, 120].map((a) => (
              <line key={a} x1={cx} y1="120" x2={cx} y2="180"
                    stroke="var(--muted)" strokeWidth="2" opacity="0.5"
                    transform={`rotate(${a} ${cx} 150)`} />
            ))}
          </g>
          <circle cx={cx} cy="150" r="10" fill="#0b1017" stroke="var(--telemetry)" strokeWidth="2" />
        </g>
      ))}
    </svg>
  );
}
