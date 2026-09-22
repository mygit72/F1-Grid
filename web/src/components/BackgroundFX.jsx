// Original, code-only animated background: a faint telemetry grid that drifts and
// a slow light scan. Subtle by design (low opacity, masked) so data stays
// readable, and hidden entirely under prefers-reduced-motion (see index.css).
export default function BackgroundFX() {
  return (
    <div className="bg-fx" aria-hidden="true">
      <div className="bg-grid" />
      <div className="bg-scan" />
    </div>
  );
}
