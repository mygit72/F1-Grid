import { motion, AnimatePresence } from "framer-motion";
import DriverPhoto from "./DriverPhoto";
import { getDriverProfile, getTeamStyle } from "../lib/drivers";

/**
 * Two columns, same row height: what you typed in (left) vs what the model
 * predicted (right), with a connecting delta badge showing how far each
 * driver moved. This is the literal "show me my grid and what I predicted"
 * comparison, kept as two lists rather than merging them into one animated
 * tower, so the INPUT is never silently overwritten by the OUTPUT.
 */
export default function GridComparison({ yourGrid, predictedFinish }) {
  const deltaFor = (driver) => {
    const inPos = yourGrid.find((g) => g.driver === driver)?.position;
    const outPos = predictedFinish.find((p) => p.driver === driver)?.predicted_position;
    if (inPos == null || outPos == null) return null;
    return inPos - outPos; // positive = gained places
  };

  return (
    <div className="grid-comparison">
      <div className="grid-comparison__column">
        <div className="grid-comparison__heading"><div className="eyebrow">YOUR GRID</div><span>{yourGrid.length} DRIVERS</span></div>
        <Column rows={yourGrid.map((g) => ({ pos: g.position, driver: g.driver, team: g.team }))} />
      </div>
      <div className="grid-comparison__column">
        <div className="grid-comparison__heading"><div className="eyebrow"><span className="dot" /> PREDICTED FINISH</div><span>{predictedFinish.length} DRIVERS</span></div>
        <Column
          rows={predictedFinish.map((p) => ({
            pos: p.predicted_position,
            driver: p.driver,
            team: p.team,
            delta: deltaFor(p.driver),
            prior: p.prior, // set only for no-history (debut) entries
          }))}
          showDelta
        />
      </div>
    </div>
  );
}

function Column({ rows, showDelta }) {
  return (
    <div className="panel grid-comparison__list scrollbar-thin">
      <AnimatePresence initial={false}>
        {rows.map((r) => (
          <motion.div
            layout
            key={r.driver + r.pos}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ type: "spring", stiffness: 380, damping: 32 }}
            className="grid-comparison-row"
            style={{ "--team": getTeamStyle(r.team, r.driver).accent, "--team-deep": getTeamStyle(r.team, r.driver).deep }}
          >
            <span className="grid-comparison-row__position">{String(r.pos).padStart(2, "0")}</span>
            <DriverPhoto code={r.driver} team={r.team} className="grid-comparison-row__portrait" />
            <span className="grid-comparison-row__driver"><strong>{getDriverProfile(r.driver).name}</strong><small>{getTeamStyle(r.team, r.driver).name}</small></span>
            {r.prior && (
              <span
                title={r.prior}
                style={{
                  fontSize: "0.6rem",
                  fontWeight: 700,
                  letterSpacing: "0.04em",
                  padding: "2px 6px",
                  borderRadius: 4,
                  color: "var(--muted)",
                  border: "1px solid var(--border, #333)",
                  whiteSpace: "nowrap",
                }}
              >
                NO HISTORY: DEBUT PRIOR
              </span>
            )}
            {showDelta && r.delta != null && r.delta !== 0 && (
              <span
                className="mono"
                style={{
                  fontSize: "0.75rem",
                  fontWeight: 700,
                  color: r.delta > 0 ? "var(--good)" : "var(--signal)",
                }}
              >
                {r.delta > 0 ? `▲${r.delta}` : `▼${Math.abs(r.delta)}`}
              </span>
            )}
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}
