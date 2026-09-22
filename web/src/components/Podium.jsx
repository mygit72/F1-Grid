import { useCountUp } from "../lib/useCountUp";

const MEDAL = { 1: "\u{1F947}", 2: "\u{1F948}", 3: "\u{1F949}" };

// The predicted podium, visually separated with medal treatment to match the
// GitHub release notes. Win probability counts up to its final value.
export default function Podium({ predictions }) {
  const top3 = [...predictions]
    .sort((a, b) => a.predicted_position - b.predicted_position)
    .slice(0, 3);
  return (
    <div className="podium">
      {top3.map((p) => (
        <PodiumCard key={p.driver} p={p} />
      ))}
    </div>
  );
}

function PodiumCard({ p }) {
  const pct = useCountUp((p.win_prob ?? 0) * 100, { decimals: 1 });
  const pos = p.predicted_position;
  return (
    <div className={`podium-card glass p${pos}`}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span className="medal" aria-hidden="true">{MEDAL[pos]}</span>
        <span className="mono" style={{ color: "var(--muted)", fontSize: "0.7rem" }}>P{pos}</span>
      </div>
      <div className="drv" style={{ marginTop: 6 }}>{p.driver}</div>
      <div style={{ color: "var(--muted)", fontSize: "0.78rem", minHeight: "1.1em" }}>{p.team || ""}</div>
      <div style={{ marginTop: 8, fontSize: "0.72rem", color: "var(--muted)" }}>
        WIN <span className="prob">{pct}%</span>
      </div>
    </div>
  );
}
