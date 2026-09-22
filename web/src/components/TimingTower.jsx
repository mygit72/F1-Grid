import { useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";

const TEAM_COLORS = {
  RBR: "#3671C6", FER: "#F91536", MER: "#27F4D2", MCL: "#FF8000",
  AST: "#229971", ALP: "#2293D1", WIL: "#37BEDD", HAA: "#B6BABD",
  SAU: "#52E252", RB: "#6692FF",
};
const teamColor = (team) => TEAM_COLORS[team] ?? "#7C8794";

/**
 * The signature visual: a timing-tower row list keyed by driver, so when
 * predicted_position changes the row springs (Framer Motion `layout`) to its new
 * slot. Position swaps are made dramatic: any change pulses the row, and a big
 * mover (3+ places) gets a trailing streak plus a brief motion blur. Rows enter
 * in sequence on first load. Team colours are generic accents, not liveries.
 */
export default function TimingTower({ predictions, highlightDriver, onSelectDriver }) {
  const sorted = [...predictions].sort(
    (a, b) => a.predicted_position - b.predicted_position
  );
  const maxWin = Math.max(...sorted.map((p) => p.win_prob ?? 0), 0.01);

  // Track previous positions to detect movers (delta > 0 means moved up).
  const prev = useRef(null);
  const prevMap = prev.current;
  const deltas = {};
  for (const p of sorted) {
    const before = prevMap ? prevMap[p.driver] : undefined;
    deltas[p.driver] = before == null ? 0 : before - p.predicted_position;
  }
  useEffect(() => {
    const m = {};
    for (const p of sorted) m[p.driver] = p.predicted_position;
    prev.current = m;
  });
  const firstLoad = prevMap == null;

  return (
    <div className="panel glass scrollbar-thin" data-testid="timing-tower"
         style={{ padding: 10, overflowY: "auto", maxHeight: 560 }}>
      <AnimatePresence initial={false}>
        {sorted.map((p, i) => {
          const delta = deltas[p.driver] || 0;
          const big = Math.abs(delta) >= 3;
          // A key that changes on a position change so the streak/pulse replay.
          const fxKey = `${p.driver}-${p.predicted_position}`;
          const cls = [
            "tt-row-inner",
            firstLoad ? "tt-enter" : "",
            delta !== 0 ? "tt-pulse" : "",
            big ? "tt-streak tt-blur" : "",
          ].join(" ").trim();
          return (
            <motion.div
              key={p.driver}
              data-testid="timing-row"
              data-driver={p.driver}
              layout
              transition={{ type: "spring", stiffness: 420, damping: 34, mass: 0.9 }}
              onClick={() => onSelectDriver?.(p.driver)}
              style={{ marginBottom: 5 }}
            >
              <div
                key={fxKey}
                className={cls}
                style={{
                  display: "flex", alignItems: "center", gap: 12, padding: "9px 12px",
                  animationDelay: firstLoad ? `${i * 0.04}s` : undefined,
                  cursor: onSelectDriver ? "pointer" : "default",
                  background: highlightDriver === p.driver ? "var(--panel-raised)" : "transparent",
                  border: `1px solid ${highlightDriver === p.driver ? "var(--telemetry)" : "transparent"}`,
                  borderRadius: 6,
                }}
              >
                <div className="mono" style={{ width: 28, fontWeight: 700, fontSize: "1.05rem", color: "var(--signal)" }}>
                  {String(p.predicted_position).padStart(2, "0")}
                </div>
                {delta !== 0 && (
                  <span className="mono" title="places gained/lost vs last update"
                        style={{ width: 20, fontSize: "0.62rem", color: delta > 0 ? "var(--good)" : "var(--signal)" }}>
                    {delta > 0 ? `▲${delta}` : `▼${Math.abs(delta)}`}
                  </span>
                )}
                <div style={{ width: 4, height: 26, borderRadius: 2, background: teamColor(p.team) }} />
                <div style={{ width: 58, fontWeight: 700, letterSpacing: "0.04em" }}>{p.driver}</div>
                <div style={{ flex: 1, color: "var(--muted)", fontSize: "0.82rem" }}>{p.team ?? ""}</div>
                <div style={{ width: 90 }}>
                  <div style={{ height: 4, background: "var(--line)", borderRadius: 2, overflow: "hidden" }}>
                    <motion.div layout style={{ height: "100%", background: "var(--telemetry)" }}
                                animate={{ width: `${100 * (p.win_prob ?? 0) / maxWin}%` }}
                                transition={{ type: "spring", stiffness: 200, damping: 26 }} />
                  </div>
                </div>
                <div className="mono" style={{ width: 54, textAlign: "right", fontSize: "0.85rem" }}>
                  {((p.win_prob ?? 0) * 100).toFixed(1)}%
                </div>
                {p.dnf_prob != null && p.dnf_prob > 0.12 && (
                  <div className="mono" title="Elevated DNF probability"
                       style={{ width: 14, textAlign: "center", color: "var(--warn)", fontSize: "0.8rem" }}>!</div>
                )}
              </div>
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}
