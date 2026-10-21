import { useCountUp } from "../lib/useCountUp";
import DriverPhoto from "./DriverPhoto";
import { getDriverProfile, getTeamStyle } from "../lib/drivers";

export default function Podium({ predictions, season }) {
  const top3 = [...predictions]
    .sort((a, b) => a.predicted_position - b.predicted_position)
    .slice(0, 3);
  const [winner, ...runners] = top3;

  return (
    <section className="podium-wrap" aria-label="Predicted podium">
      {winner && <TopPick prediction={winner} total={predictions.length} season={season} />}
      {runners.length > 0 && (
        <div className="podium-runners">
          {runners.map((prediction, index) => (
            <RunnerCard key={prediction.driver} prediction={prediction} season={season} delay={0.08 + index * 0.06} />
          ))}
        </div>
      )}
    </section>
  );
}

function TopPick({ prediction, total, season }) {
  const profile = getDriverProfile(prediction.driver);
  const team = getTeamStyle(prediction.team, prediction.driver);
  const pct = useCountUp((prediction.win_prob ?? 0) * 100, { decimals: 1 });
  const podiumPct = ((prediction.podium_prob ?? 0) * 100).toFixed(1);

  return (
    <article className="top-pick card-reveal" style={{ "--team": team.accent, "--team-deep": team.deep }}>
      <div className="top-pick__image-wrap">
        <span className="top-pick__image-label"><i /> MODEL'S TOP PICK</span>
        <DriverPhoto code={prediction.driver} team={prediction.team} className="top-pick__portrait" eager />
        <span className="top-pick__number">{season === 2026 && profile.number ? `#${profile.number}` : prediction.driver}</span>
      </div>
      <div className="top-pick__info">
        <div className="driver-teamline"><span className="livery-mark" /><span>{team.name}</span><span className="driver-nationality">{profile.nationality || "F1"}</span></div>
        <div className="top-pick__position">PREDICTED WINNER <span>01 / {String(total).padStart(2, "0")}</span></div>
        <DriverName profile={profile} className="top-pick__name" />
        <div className="top-pick__metrics">
          <div className="top-pick__win">
            <span className="top-pick__score">{pct}<span className="top-pick__score-unit">%</span></span>
            <span className="top-pick__score-label">Win probability</span>
          </div>
          <div className="top-pick__secondary">
            <span>Podium chance</span>
            <strong>{podiumPct}%</strong>
          </div>
        </div>
        <div className="top-pick__photo-credit"><a href="https://www.formula1.com/en/drivers" target="_blank" rel="noreferrer">Official 2026 driver portrait ↗</a></div>
      </div>
      <div className="top-pick__livery" aria-hidden="true" />
    </article>
  );
}

function RunnerCard({ prediction, season, delay }) {
  const profile = getDriverProfile(prediction.driver);
  const team = getTeamStyle(prediction.team, prediction.driver);
  const pct = useCountUp((prediction.win_prob ?? 0) * 100, { decimals: 1 });

  return (
    <article className="runner-card card-reveal" style={{ "--team": team.accent, "--team-deep": team.deep, animationDelay: `${delay}s` }}>
      <DriverPhoto code={prediction.driver} team={prediction.team} className="runner-card__portrait" />
      <div className="runner-card__content">
        <div className="runner-card__topline"><span className="runner-card__rank">P{prediction.predicted_position}</span><span className="runner-card__number">{season === 2026 && profile.number ? `#${profile.number}` : prediction.driver}</span></div>
        <DriverName profile={profile} className="runner-card__name" />
        <div className="runner-card__team"><span className="livery-mark" />{team.name}</div>
        <div className="runner-card__prob"><span>WIN CHANCE</span><strong>{pct}%</strong></div>
      </div>
    </article>
  );
}

function DriverName({ profile, className }) {
  const content = <span className={className}>{profile.name}</span>;
  if (!profile.profileUrl) return content;
  return <a className="driver-profile-link" href={profile.profileUrl} target="_blank" rel="noreferrer">{content}</a>;
}
