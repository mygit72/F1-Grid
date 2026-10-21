import { useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import DriverPhoto from "./DriverPhoto";
import { getDriverProfile, getTeamStyle } from "../lib/drivers";

export default function TimingTower({ predictions, season, highlightDriver, onSelectDriver }) {
  const sorted = [...predictions].sort((a, b) => a.predicted_position - b.predicted_position);
  const maxWin = Math.max(...sorted.map((prediction) => prediction.win_prob ?? 0), 0.01);
  const previousPositions = useRef(null);
  const previous = previousPositions.current;
  const deltas = {};

  for (const prediction of sorted) {
    const before = previous?.[prediction.driver];
    deltas[prediction.driver] = before == null ? 0 : before - prediction.predicted_position;
  }

  useEffect(() => {
    previousPositions.current = Object.fromEntries(sorted.map((prediction) => [prediction.driver, prediction.predicted_position]));
  });

  const firstLoad = previous == null;

  return (
    <section className="panel glass timing-panel" data-testid="timing-tower">
      <div className="panel-heading">
        <div>
          <div className="eyebrow"><span className="dot" /> PREDICTED ORDER</div>
          <h3>Race timing tower</h3>
        </div>
        <div className="timing-panel__count"><strong>{String(sorted.length).padStart(2, "0")}</strong><span>DRIVERS</span></div>
      </div>
      <div className="timing-columns" aria-hidden="true"><span>POS / MOVE</span><span>DRIVER / TEAM</span><span>WIN CHANCE</span><span>%</span></div>
      <div className="timing-list scrollbar-thin">
        <AnimatePresence initial={false}>
          {sorted.map((prediction, index) => {
            const delta = deltas[prediction.driver] || 0;
            const isSelected = highlightDriver === prediction.driver;
            const team = getTeamStyle(prediction.team, prediction.driver);
            const profile = getDriverProfile(prediction.driver);
            const width = `${(100 * (prediction.win_prob ?? 0)) / maxWin}%`;

            return (
              <motion.button
                type="button"
                key={prediction.driver}
                data-testid="timing-row"
                data-driver={prediction.driver}
                layout
                initial={firstLoad ? { opacity: 0, x: -14 } : false}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 16 }}
                transition={{ type: "spring", stiffness: 420, damping: 34, mass: 0.9, delay: firstLoad ? index * 0.025 : 0 }}
                onClick={() => onSelectDriver?.(prediction.driver)}
                aria-pressed={isSelected}
                className={`timing-row${isSelected ? " is-selected" : ""}`}
                style={{ "--team": team.accent, "--team-deep": team.deep }}
              >
                <span className="timing-row__position">
                  <strong>{String(prediction.predicted_position).padStart(2, "0")}</strong>
                  {delta !== 0 && <small className={delta > 0 ? "move-up" : "move-down"}>{delta > 0 ? `▲${delta}` : `▼${Math.abs(delta)}`}</small>}
                </span>
                <span className="timing-row__driver">
                  <DriverPhoto code={prediction.driver} team={prediction.team} className="timing-row__portrait" />
                  <span className="timing-row__driver-copy">
                    <strong>{profile.name}</strong>
                    <span><i /> {team.name}{season === 2026 && profile.number ? <b>#{profile.number}</b> : null}</span>
                  </span>
                </span>
                <span className="timing-row__bar" aria-hidden="true"><motion.i animate={{ width }} transition={{ type: "spring", stiffness: 200, damping: 26 }} /></span>
                <span className="timing-row__probability">{((prediction.win_prob ?? 0) * 100).toFixed(1)}%</span>
                {prediction.dnf_prob != null && prediction.dnf_prob > 0.12 && <span className="timing-row__warning" title="Elevated DNF probability">!</span>}
              </motion.button>
            );
          })}
        </AnimatePresence>
      </div>
      <div className="timing-panel__footer"><span><i /> TEAM LIVERY KEY</span><span>ROW ORDERED BY EXPECTED FINISH</span></div>
    </section>
  );
}
