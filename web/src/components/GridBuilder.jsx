import { useState } from "react";
import { motion } from "framer-motion";
import DriverPhoto from "./DriverPhoto";
import { getDriverProfile, getTeamStyle } from "../lib/drivers";

// A complete 2026 roster in a sample order. Users can edit the rows to build
// any hypothetical starting grid before passing it to the race model.
const DEFAULT_ROWS = [
  { driver: "VER", team: "Red Bull" }, { driver: "ANT", team: "Mercedes" },
  { driver: "NOR", team: "McLaren" }, { driver: "LEC", team: "Ferrari" },
  { driver: "PIA", team: "McLaren" }, { driver: "HAM", team: "Ferrari" },
  { driver: "RUS", team: "Mercedes" }, { driver: "LAW", team: "RB F1 Team" },
  { driver: "HAD", team: "Red Bull" }, { driver: "HUL", team: "Audi" },
  { driver: "BEA", team: "Haas F1 Team" }, { driver: "COL", team: "Alpine F1 Team" },
  { driver: "OCO", team: "Haas F1 Team" }, { driver: "GAS", team: "Alpine F1 Team" },
  { driver: "LIN", team: "RB F1 Team" }, { driver: "BOR", team: "Audi" },
  { driver: "ALO", team: "Aston Martin" }, { driver: "SAI", team: "Williams" },
  { driver: "PER", team: "Cadillac F1 Team" }, { driver: "ALB", team: "Williams" },
  { driver: "BOT", team: "Cadillac F1 Team" }, { driver: "STR", team: "Aston Martin" },
];

export default function GridBuilder({ onPredict, loading }) {
  const [rows, setRows] = useState(DEFAULT_ROWS);

  const updateRow = (index, field, value) => {
    const next = [...rows];
    next[index] = { ...next[index], [field]: field === "driver" ? value.toUpperCase() : value };
    setRows(next);
  };

  const addRow = () => setRows([...rows, { driver: "", team: "" }]);
  const removeRow = (index) => setRows(rows.filter((_, rowIndex) => rowIndex !== index));

  return (
    <section className="panel lab-panel grid-builder">
      <div className="grid-builder__heading">
        <div><div className="eyebrow"><span className="dot" /> YOUR GRID</div><h3>Build a starting order</h3></div>
        <span className="round-token">{String(rows.length).padStart(2, "0")} CARS</span>
      </div>
      <p className="grid-builder__intro">The 2026 roster is prefilled as a template. Edit the order and team names, then let the model predict the finish from this exact lineup.</p>
      <div className="grid-builder__columns" aria-hidden="true"><span>GRID</span><span>DRIVER PROFILE</span><span>TEAM</span><span /></div>

      <div className="grid-builder__list scrollbar-thin">
        {rows.map((row, index) => {
          const profile = getDriverProfile(row.driver);
          const teamStyle = getTeamStyle(row.team, row.driver);
          return (
            <div className="grid-builder-row" key={index} style={{ "--team": teamStyle.accent, "--team-deep": teamStyle.deep }}>
              <span className="grid-builder-row__position">{String(index + 1).padStart(2, "0")}</span>
              <DriverPhoto code={row.driver} team={row.team} className="grid-builder-row__portrait" />
              <div className="grid-builder-row__driver">
                <input value={row.driver} onChange={(event) => updateRow(index, "driver", event.target.value)} aria-label={`Driver code for grid position ${index + 1}`} placeholder="VER" maxLength={3} />
                <span>{profile.name}{profile.number ? <small> · #{profile.number}</small> : null}</span>
              </div>
              <input className="grid-builder-row__team" value={row.team} onChange={(event) => updateRow(index, "team", event.target.value)} aria-label={`Team for grid position ${index + 1}`} placeholder="Team name" maxLength={40} />
              <button className="grid-builder-row__remove" onClick={() => removeRow(index)} aria-label={`Remove grid row ${index + 1}`} title="Remove row">×</button>
            </div>
          );
        })}
      </div>

      <div className="grid-builder__actions">
        <button type="button" onClick={addRow} className="lab-reset">+ Add driver</button>
        <motion.button type="button" whileTap={{ scale: 0.98 }} onClick={() => onPredict(rows.filter((row) => row.driver))} disabled={loading} className="lab-run">
          {loading ? "Predicting…" : "Predict this grid"}<span aria-hidden="true">↗</span>
        </motion.button>
      </div>
    </section>
  );
}
