// Circuit strategy-disruption meter, shown ALONGSIDE the prediction (never fed
// into it). Held-out validation did not support a confidence claim, so the API
// labels it "Strategy complexity" with is_confidence=false. This component shows
// exactly what the API sends as a labelled Low/Medium/High gauge and makes NO
// confidence claim. New venues arrive as state="no_history" and are shown as such.
const LEVELS = ["Low", "Medium", "High"];
const LEVEL_COLOR = { Low: "var(--muted)", Medium: "#d9a441", High: "#e0533d" };

export default function StrategyMeter({ meter }) {
  if (!meter) return null;

  const noHistory = meter.state === "no_history";
  const active = LEVELS.indexOf(meter.level);
  const accent = noHistory ? "var(--muted)" : (LEVEL_COLOR[meter.level] || "var(--muted)");
  const badge = noHistory
    ? "No history"
    : `${meter.label}${meter.level ? `: ${meter.level}` : ""}`;

  return (
    <div className="panel glass" style={{ padding: 16, marginBottom: 16 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ width: 10, height: 10, borderRadius: "50%", background: accent, boxShadow: `0 0 10px ${accent}` }} />
          <span style={{ fontWeight: 600, fontSize: "0.9rem", letterSpacing: "0.02em" }}>{badge}</span>
        </div>
        {meter.is_confidence === false && !noHistory && (
          <span style={{ color: "var(--muted)", fontSize: "0.7rem" }}>
            circuit description, not a confidence score
          </span>
        )}
      </div>

      {/* Low / Medium / High gauge. Not a probability or confidence: a labelled
          description of how much strategy tends to reshuffle the order here. */}
      <div className="gauge-track" role="img"
           aria-label={noHistory ? "Strategy complexity: no history for this circuit"
                                 : `Strategy complexity level ${meter.level || "unknown"} of Low, Medium, High`}>
        {LEVELS.map((lvl, i) => (
          <div key={lvl} className="gauge-seg" data-on={!noHistory && i <= active}
               style={{ background: (!noHistory && i <= active) ? LEVEL_COLOR[lvl] : "var(--line)", color: LEVEL_COLOR[lvl] }} />
        ))}
      </div>
      <div className="gauge-labels"><span>LOW</span><span>MEDIUM</span><span>HIGH</span></div>

      <p style={{ color: "var(--muted)", fontSize: "0.78rem", margin: "10px 0 0" }}>{meter.reason}</p>
    </div>
  );
}
