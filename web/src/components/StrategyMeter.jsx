// Circuit strategy-disruption meter, shown ALONGSIDE the prediction (never fed
// into it). Held-out validation did not support a confidence claim, so the API
// labels it "Strategy complexity" with is_confidence=false. This component shows
// exactly what the API sends and makes no confidence claim of its own. New
// venues arrive as state="no_history" and are labelled as such, not guessed.
export default function StrategyMeter({ meter }) {
  if (!meter) return null;

  const levelColor = {
    Low: "var(--muted)",
    Medium: "#d9a441",
    High: "#e0533d",
  };

  const noHistory = meter.state === "no_history";
  const badge = noHistory
    ? "No history"
    : `${meter.label}${meter.level ? `: ${meter.level}` : ""}`;
  const accent = noHistory ? "var(--muted)" : (levelColor[meter.level] || "var(--muted)");

  return (
    <div className="panel" style={{ padding: 14, marginBottom: 16 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <span
          style={{
            display: "inline-block", width: 10, height: 10, borderRadius: "50%",
            background: accent,
          }}
        />
        <span style={{ fontWeight: 600, fontSize: "0.85rem", letterSpacing: "0.02em" }}>
          {badge}
        </span>
        {meter.is_confidence === false && !noHistory && (
          <span style={{ color: "var(--muted)", fontSize: "0.7rem" }}>
            (circuit description, not a confidence claim)
          </span>
        )}
      </div>
      <p style={{ color: "var(--muted)", fontSize: "0.78rem", margin: "8px 0 0" }}>
        {meter.reason}
      </p>
    </div>
  );
}
