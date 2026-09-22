// Loading state for a prediction: reads like a system booting (telemetry lines
// filling in). It is ONLY a placeholder shown while the request is in flight, so
// it never delays the result: the moment data arrives the real content replaces
// it. Sized to the real layout to avoid any layout shift.
export default function PredictionSkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading prediction">
      <div className="podium" style={{ marginBottom: 16 }}>
        {[1, 2, 3].map((i) => (
          <div key={i} className="skeleton" style={{ height: 116, borderRadius: 12 }} />
        ))}
      </div>
      <div className="skeleton" style={{ height: 92, borderRadius: 12, marginBottom: 16 }} />
      <div className="race-grid" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <div className="panel" style={{ padding: 10, height: 560 }}>
          <div className="mono" style={{ color: "var(--telemetry)", fontSize: "0.7rem", padding: "4px 8px", letterSpacing: "0.12em" }}>
            BOOTING TELEMETRY...
          </div>
          {Array.from({ length: 12 }).map((_, i) => (
            <div key={i} className="boot-line" style={{ width: `${92 - i * 4}%`, animationDelay: `${i * 0.08}s` }} />
          ))}
        </div>
        <div className="skeleton" style={{ height: 360, borderRadius: 12 }} />
      </div>
    </div>
  );
}
