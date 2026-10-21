import { useCountUp } from "../lib/useCountUp";

// Darker variants of each team's accent so it stays readable as TEXT on a
// white card and as a white-text circle fill (the vivid versions in
// TimingTower/TrackMap are tuned for dark surfaces instead; these are not).
const TEAM_COLORS = {
  RBR: "#2A5FBD", FER: "#D1172E", MER: "#1E8E7A", MCL: "#B35900",
  AST: "#1D7A5A", ALP: "#1C74AE", WIL: "#0E7490", HAA: "#6B665F",
  SAU: "#1A8A3F", RB: "#3A5FD0",
};
const teamColor = (team) => TEAM_COLORS[team] ?? "#6B665F";

// The predicted race winner gets an editorial "top pick" spotlight (name,
// team, win probability as a giant score); P2/P3 sit below as smaller
// runner-up cards. Win probability counts up to its final value.
export default function Podium({ predictions }) {
  const top3 = [...predictions]
    .sort((a, b) => a.predicted_position - b.predicted_position)
    .slice(0, 3);
  const [winner, ...runners] = top3;

  return (
    <div className="podium-wrap">
      {winner && <TopPick p={winner} />}
      {runners.length > 0 && (
        <div className="podium-runners">
          {runners.map((p, i) => (
            <RunnerCard key={p.driver} p={p} delay={0.08 + i * 0.06} />
          ))}
        </div>
      )}
    </div>
  );
}

function TopPick({ p }) {
  const pct = useCountUp((p.win_prob ?? 0) * 100, { decimals: 1 });
  const color = teamColor(p.team);
  return (
    <div className="top-pick card-reveal" style={{ "--team": color }}>
      <div className="top-pick__monogram">{(p.driver || "?").slice(0, 2)}</div>
      <div className="top-pick__label">Predicted winner</div>
      <div className="top-pick__team">{p.team || ""}</div>
      <div className="top-pick__name">{p.driver}</div>
      <div className="top-pick__row">
        <div>
          <span className="top-pick__score">{pct}<span className="top-pick__score-unit">%</span></span>
          <div className="top-pick__score-label">Win probability</div>
        </div>
      </div>
    </div>
  );
}

function RunnerCard({ p, delay }) {
  const pct = useCountUp((p.win_prob ?? 0) * 100, { decimals: 1 });
  const pos = p.predicted_position;
  const color = teamColor(p.team);
  return (
    <div className="runner-card card-reveal" style={{ "--team": color, animationDelay: `${delay}s` }}>
      <span className="rank">P{pos}</span>
      <div className="drv">{p.driver}</div>
      <div className="team">{p.team || ""}</div>
      <div className="prob">WIN <span className="mono">{pct}%</span></div>
    </div>
  );
}
