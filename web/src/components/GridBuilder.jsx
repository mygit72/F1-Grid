import { useState } from "react";
import { motion } from "framer-motion";

const DEFAULT_ROWS = [
  { driver: "VER", team: "RBR" }, { driver: "PER", team: "RBR" },
  { driver: "LEC", team: "FER" }, { driver: "SAI", team: "FER" },
  { driver: "HAM", team: "MER" }, { driver: "RUS", team: "MER" },
  { driver: "NOR", team: "MCL" }, { driver: "PIA", team: "MCL" },
  { driver: "ALO", team: "AST" }, { driver: "STR", team: "AST" },
];

/**
 * Lets you type out an actual starting grid (driver + team per row, in grid
 * order) and asks the race model to predict the finishing order FROM that
 * exact lineup - a real "what I put in vs. what came out" comparison, shown
 * side by side rather than just replacing one with the other.
 */
export default function GridBuilder({ onPredict, loading }) {
  const [rows, setRows] = useState(DEFAULT_ROWS);

  const updateRow = (i, field, value) => {
    const next = [...rows];
    next[i] = { ...next[i], [field]: value.toUpperCase() };
    setRows(next);
  };

  const addRow = () => setRows([...rows, { driver: "", team: "" }]);
  const removeRow = (i) => setRows(rows.filter((_, idx) => idx !== i));

  return (
    <div className="panel lab-panel" style={{ padding: 16 }}>
      <div className="eyebrow" style={{ marginBottom: 10 }}>
        <span className="dot" /> YOUR GRID
      </div>
      <p style={{ color: "var(--muted)", fontSize: "0.78rem", marginTop: 0 }}>
        Enter a starting grid in order (P1 first). The race model predicts a
        finishing order from exactly this lineup - useful for testing
        hypothetical grids, not just historical ones.
      </p>

      <div className="scrollbar-thin" style={{ maxHeight: 380, overflowY: "auto" }}>
        {rows.map((row, i) => (
          <div
            key={i}
            style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}
          >
            <span className="mono" style={{ width: 26, color: "var(--signal)", fontWeight: 700 }}>
              {String(i + 1).padStart(2, "0")}
            </span>
            <input
              value={row.driver}
              onChange={(e) => updateRow(i, "driver", e.target.value)}
              placeholder="VER"
              maxLength={3}
              style={inputStyle(64)}
            />
            <input
              value={row.team}
              onChange={(e) => updateRow(i, "team", e.target.value)}
              placeholder="RBR"
              maxLength={4}
              style={inputStyle(64)}
            />
            <button onClick={() => removeRow(i)} style={removeBtnStyle}>
              ×
            </button>
          </div>
        ))}
      </div>

      <div style={{ display: "flex", gap: 8, marginTop: 14 }}>
        <button onClick={addRow} className="lab-reset">
          + Add row
        </button>
        <motion.button
          whileTap={{ scale: 0.97 }}
          onClick={() => onPredict(rows.filter((r) => r.driver))}
          disabled={loading}
          className="lab-run"
          style={{ flex: 1 }}
        >
          {loading ? "Predicting…" : "Predict from this grid"}
        </motion.button>
      </div>
    </div>
  );
}

const inputStyle = (width) => ({
  width,
  background: "#fff",
  border: "1px solid rgba(20,18,14,0.2)",
  borderRadius: 8,
  color: "var(--text)",
  padding: "6px 8px",
  fontFamily: "var(--font-body)",
  fontWeight: 600,
  fontSize: "0.8rem",
});

const removeBtnStyle = {
  background: "none",
  border: "none",
  color: "var(--muted)",
  cursor: "pointer",
  fontSize: "1rem",
};
