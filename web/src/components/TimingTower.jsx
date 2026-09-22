import { motion, AnimatePresence } from "framer-motion";

const TEAM_COLORS = {
  RBR: "#3671C6", FER: "#F91536", MER: "#27F4D2", MCL: "#FF8000",
  AST: "#229971", ALP: "#2293D1", WIL: "#37BEDD", HAA: "#B6BABD",
  SAU: "#52E252", RB: "#6692FF",
};
const teamColor = (team) => TEAM_COLORS[team] ?? "#7C8794";

/**
 * The signature visual moment: a timing-tower row list where each row is
 * keyed by driver, so when predicted_position changes (rain slider, scenario
 * override, grid toggle) Framer Motion's `layout` animates the row sliding to
 * its new vertical slot - a spring, broadcast-overlay-style reorder, not a
 * re-render snap.
 */
export default function TimingTower({ predictions, highlightDriver, onSelectDriver }) {
  const sorted = [...predictions].sort(
    (a, b) => a.predicted_position - b.predicted_position
  );
  const maxWin = Math.max(...sorted.map((p) => p.win_prob ?? 0), 0.01);

  return (
    <div className="panel scrollbar-thin" style={{ padding: 10, overflowY: "auto", maxHeight: 560 }}>
      <AnimatePresence initial={false}>
        {sorted.map((p) => (
          <motion.div
            key={p.driver}
            layout
            transition={{ type: "spring", stiffness: 420, damping: 34, mass: 0.9 }}
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            onClick={() => onSelectDriver?.(p.driver)}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 12,
              padding: "9px 12px",
              marginBottom: 5,
              borderRadius: 6,
              cursor: onSelectDriver ? "pointer" : "default",
              background: highlightDriver === p.driver ? "var(--panel-raised)" : "transparent",
              border: `1px solid ${highlightDriver === p.driver ? "var(--telemetry)" : "transparent"}`,
            }}
          >
            <div
              className="mono"
              style={{ width: 28, fontWeight: 700, fontSize: "1.05rem", color: "var(--signal)" }}
            >
              {String(p.predicted_position).padStart(2, "0")}
            </div>

            <div
              style={{ width: 4, height: 26, borderRadius: 2, background: teamColor(p.team) }}
            />

            <div style={{ width: 58, fontWeight: 700, letterSpacing: "0.04em" }}>
              {p.driver}
            </div>

            <div style={{ flex: 1, color: "var(--muted)", fontSize: "0.82rem" }}>
              {p.team ?? ""}
            </div>

            <div style={{ width: 90 }}>
              <div style={{ height: 4, background: "var(--line)", borderRadius: 2, overflow: "hidden" }}>
                <motion.div
                  layout
                  style={{ height: "100%", background: "var(--telemetry)" }}
                  animate={{ width: `${100 * (p.win_prob ?? 0) / maxWin}%` }}
                  transition={{ type: "spring", stiffness: 200, damping: 26 }}
                />
              </div>
            </div>

            <div className="mono" style={{ width: 54, textAlign: "right", fontSize: "0.85rem" }}>
              {((p.win_prob ?? 0) * 100).toFixed(1)}%
            </div>

            {p.dnf_prob != null && p.dnf_prob > 0.12 && (
              <div
                className="mono"
                title="Elevated DNF probability"
                style={{ width: 14, textAlign: "center", color: "var(--warn)", fontSize: "0.8rem" }}
              >
                !
              </div>
            )}
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}
