import { useEffect, useMemo, useState } from "react";
import DriverPhoto from "./DriverPhoto";
import { DRIVER_PROFILES, TEAM_STYLES, getTeamStyle } from "../lib/drivers";

const DRIVERS = Object.entries(DRIVER_PROFILES)
  .map(([code, profile]) => ({ ...profile, code }))
  .sort((a, b) => a.number - b.number);

const TEAMS = [...new Set(DRIVERS.map((driver) => driver.teamKey))]
  .map((key) => ({ key, ...TEAM_STYLES[key] }))
  .sort((a, b) => a.name.localeCompare(b.name));

export default function DriverLineup({ initialDriver = null }) {
  const [search, setSearch] = useState("");
  const [teamFilter, setTeamFilter] = useState("all");
  const [selectedCode, setSelectedCode] = useState(null);

  useEffect(() => {
    if (initialDriver) setSelectedCode(String(initialDriver).toUpperCase());
  }, [initialDriver]);

  useEffect(() => {
    if (!selectedCode) return undefined;
    const closeOnEscape = (event) => {
      if (event.key === "Escape") setSelectedCode(null);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [selectedCode]);

  const filteredDrivers = useMemo(() => {
    const query = search.trim().toLowerCase();
    return DRIVERS.filter((driver) => {
      const matchesTeam = teamFilter === "all" || driver.teamKey === teamFilter;
      const matchesQuery = !query || [driver.name, driver.surname, driver.code, driver.nationality, getTeamStyle(driver.teamKey).name]
        .some((value) => String(value).toLowerCase().includes(query));
      return matchesTeam && matchesQuery;
    });
  }, [search, teamFilter]);

  const selectedDriver = DRIVERS.find((driver) => driver.code === selectedCode);
  const selectedTeam = selectedDriver ? getTeamStyle(selectedDriver.teamKey, selectedDriver.code) : null;

  return (
    <section className="driver-lineup" aria-labelledby="driver-lineup-title">
      <div className="driver-lineup__intro">
        <div>
          <div className="eyebrow"><span className="dot" /> 2026 GRID <span className="eyebrow-divider">/</span> DRIVER PROFILES</div>
          <h2 id="driver-lineup-title">The full lineup<span>.</span></h2>
          <p>Explore every driver on the grid. Open a card for their race number, team, portrait, and nationality.</p>
        </div>
        <div className="driver-lineup__count"><strong>{filteredDrivers.length.toString().padStart(2, "0")}</strong><span>DRIVERS</span></div>
      </div>

      <div className="driver-lineup__filters">
        <label className="driver-search">
          <span aria-hidden="true">⌕</span>
          <input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search driver, team, or nationality" aria-label="Search drivers" />
        </label>
        <label className="driver-team-filter">
          <span>TEAM</span>
          <select value={teamFilter} onChange={(event) => setTeamFilter(event.target.value)} aria-label="Filter by team">
            <option value="all">All 11 teams</option>
            {TEAMS.map((team) => <option key={team.key} value={team.key}>{team.name}</option>)}
          </select>
        </label>
      </div>

      {filteredDrivers.length ? (
        <div className="driver-lineup__grid">
          {filteredDrivers.map((driver) => {
            const team = getTeamStyle(driver.teamKey, driver.code);
            return (
              <button
                className="driver-directory-card"
                key={driver.code}
                type="button"
                style={{ "--team": team.accent, "--team-deep": team.deep }}
                onClick={() => setSelectedCode(driver.code)}
                aria-label={`Open ${driver.name}, number ${driver.number}, ${team.name}`}
              >
                <span className="driver-directory-card__photo">
                  <DriverPhoto code={driver.code} team={team.name} className="driver-directory-card__portrait" />
                  <span className="driver-directory-card__number">{String(driver.number).padStart(2, "0")}</span>
                </span>
                <span className="driver-directory-card__meta">
                  <span className="driver-directory-card__team"><i />{team.name}</span>
                  <strong>{driver.name}</strong>
                  <span className="driver-directory-card__nationality">{driver.nationality}</span>
                  <span className="driver-directory-card__action">VIEW PROFILE <b aria-hidden="true">→</b></span>
                </span>
              </button>
            );
          })}
        </div>
      ) : (
        <div className="driver-lineup__empty"><strong>No drivers found.</strong><span>Try a different name or team.</span></div>
      )}

      {selectedDriver && selectedTeam && (
        <div className="driver-profile-overlay" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setSelectedCode(null); }}>
          <section className="driver-profile-modal" role="dialog" aria-modal="true" aria-labelledby="driver-profile-title" style={{ "--team": selectedTeam.accent, "--team-deep": selectedTeam.deep }}>
            <button className="driver-profile-modal__close" type="button" onClick={() => setSelectedCode(null)} aria-label="Close driver profile">×</button>
            <div className="driver-profile-modal__portrait-wrap">
              <DriverPhoto code={selectedDriver.code} team={selectedTeam.name} className="driver-profile-modal__portrait" eager />
              <span>#{String(selectedDriver.number).padStart(2, "0")}</span>
            </div>
            <div className="driver-profile-modal__info">
              <div className="driver-profile-modal__team"><i />{selectedTeam.name} <span>2026 DRIVER</span></div>
              <h3 id="driver-profile-title">{selectedDriver.name}</h3>
              <div className="driver-profile-modal__facts">
                <div><span>RACE NUMBER</span><strong>#{selectedDriver.number}</strong></div>
                <div><span>NATIONALITY</span><strong>{selectedDriver.nationality}</strong></div>
                <div><span>TEAM</span><strong>{selectedTeam.name}</strong></div>
              </div>
              <p>Driver profile on F1Grid · 2026 season</p>
            </div>
          </section>
        </div>
      )}
    </section>
  );
}
