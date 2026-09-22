import { motion } from "framer-motion";

const COMPOUND_COLORS = {
  SOFT: "#FF3B30",
  MEDIUM: "#FFD400",
  HARD: "#E7EAEE",
  INTER: "#2FB67C",
  WET: "#2293D1",
};

/**
 * One animated horizontal Gantt row per strategy: stints are colored by
 * compound and their width animates in on mount/update - a pit-wall-monitor
 * feel. Pit stops are rendered as the gaps between stints; they're never an
 * input, only ever a consequence of how many stints exist (matches the
 * "emergent stops" design of the underlying simulator).
 */
export default function StrategyGantt({ results, totalLaps }) {
  if (!results?.length) return null;
  const best = results[0];

  return (
    <div className="panel" style={{ padding: 16 }}>
      {results.map((r, idx) => {
        let lapCursor = 0;
        return (
          <div key={r.label} style={{ marginBottom: 18 }}>
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                marginBottom: 6,
                fontSize: "0.82rem",
              }}
            >
              <span style={{ fontWeight: 600 }}>{r.label}</span>
              <span className="mono" style={{ color: idx === 0 ? "var(--good)" : "var(--muted)" }}>
                {idx === 0 ? "FASTEST" : `+${r.gap_to_best.toFixed(1)}s`} ·{" "}
                {r.n_stops} stop{r.n_stops === 1 ? "" : "s"}
              </span>
            </div>

            <div
              style={{
                display: "flex",
                height: 22,
                borderRadius: 4,
                overflow: "hidden",
                background: "var(--void)",
                border: "1px solid var(--line)",
              }}
            >
              {/* Stint widths are approximated evenly across n_stops+1 segments
                 since the API returns the compound sequence, not exact stint
                 lap counts per segment - good enough for a visual comparison. */}
              {r.sequence.map((compound, i) => {
                const segWidth = 100 / r.sequence.length;
                return (
                  <motion.div
                    key={`${compound}-${i}`}
                    initial={{ width: 0 }}
                    animate={{ width: `${segWidth}%` }}
                    transition={{ duration: 0.5, delay: i * 0.08, ease: "easeOut" }}
                    style={{
                      background: COMPOUND_COLORS[compound] ?? "#7C8794",
                      borderRight: i < r.sequence.length - 1 ? "2px solid var(--void)" : "none",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                    }}
                    title={compound}
                  >
                    <span
                      className="mono"
                      style={{
                        fontSize: "0.62rem",
                        fontWeight: 700,
                        color: compound === "HARD" ? "#05070A" : "#05070A",
                        opacity: 0.85,
                      }}
                    >
                      {compound[0]}
                    </span>
                  </motion.div>
                );
              })}
            </div>
          </div>
        );
      })}

      <div style={{ display: "flex", gap: 14, marginTop: 4, flexWrap: "wrap" }}>
        {Object.entries(COMPOUND_COLORS).map(([name, color]) => (
          <div key={name} style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ width: 10, height: 10, borderRadius: 2, background: color }} />
            <span style={{ fontSize: "0.7rem", color: "var(--muted)" }}>{name}</span>
          </div>
        ))}
      </div>
      <p style={{ color: "var(--muted)", fontSize: "0.72rem", marginTop: 10 }}>
        Clean-air comparison over {totalLaps} laps · stops are a consequence of
        compound choice, never a manual input.
      </p>
    </div>
  );
}
