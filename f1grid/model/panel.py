"""The 2026 input panel — deep, realistic, override-driven.

A Scenario holds, for every team and driver, a full set of dials:
  Team:   car_pace, aero_efficiency, power_unit, reliability
  Driver: pace_rating, quali_rating, consistency, wet_skill, reliability_exposure

Each dial DEFAULTS to a real-data-derived value (model.defaults) and may be
overridden. The honest separation: defaults come from data; overrides are your
explicit assumptions, kept in this clearly-named object rather than baked into
the model.

apply_to_features() injects the scenario into a race's feature rows so the same
trained model can be run "as if" under 2026 inputs: it adjusts grid expectation,
form proxies, DNF rate, and attaches wet_skill for the Monte Carlo layer. The
trained model itself is untouched — we only modify its inputs, which is the
legitimate way to express a forward-looking scenario.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict

import json
import numpy as np
import pandas as pd

from f1grid import schema as S
from f1grid.model.defaults import (
    derive_driver_defaults, derive_team_defaults, derive_debut_prior,
)
from f1grid.features.build import (
    NO_HISTORY_FORM_FINISH, NO_HISTORY_FORM_GRID, NO_HISTORY_FORM_POINTS,
    NO_HISTORY_DNF_RATE, NO_HISTORY_CIRCUIT,
)

# Prior used for an unknown grid entry before real data is available (or as a
# floor if the results frame is empty). Overwritten by from_results() with the
# real 2019-2025 debut number.
_FALLBACK_DEBUT_PRIOR = {"expected_finish": 15.0, "classified_finish": 12.0,
                         "dnf_rate": 0.15, "n_debuts": 0}


@dataclass
class TeamDials:
    car_pace: float = 0.5
    aero_efficiency: float = 0.5
    power_unit: float = 0.5
    reliability: float = 0.85

    def composite(self) -> float:
        # Car strength = pace anchored, aero + PU as modifiers.
        return float(np.clip(
            0.6 * self.car_pace + 0.2 * self.aero_efficiency + 0.2 * self.power_unit,
            0.0, 1.0,
        ))


@dataclass
class DriverDials:
    pace_rating: float = 0.5
    quali_rating: float = 0.5
    consistency: float = 0.5
    wet_skill: float = 0.5
    reliability_exposure: float = 0.1

    def composite(self) -> float:
        return float(np.clip(
            0.55 * self.pace_rating + 0.30 * self.quali_rating + 0.15 * self.consistency,
            0.0, 1.0,
        ))


@dataclass
class Scenario:
    name: str = "2026 baseline"
    teams: dict = field(default_factory=dict)     # team -> TeamDials
    drivers: dict = field(default_factory=dict)   # driver code -> DriverDials
    driver_team: dict = field(default_factory=dict)  # driver -> team
    # Real-data prior for entries with no history (debut driver / new team).
    debut_prior: dict = field(default_factory=lambda: dict(_FALLBACK_DEBUT_PRIOR))

    # ── construction from real data ──
    @classmethod
    def from_results(cls, results: pd.DataFrame, name: str = "2026 baseline",
                     wet_events=None) -> "Scenario":
        td = derive_team_defaults(results)
        dd = derive_driver_defaults(results, wet_events=wet_events)
        teams = {r["team"]: TeamDials(r["car_pace"], r["aero_efficiency"],
                                      r["power_unit"], r["reliability"])
                 for _, r in td.iterrows()}
        drivers, dteam = {}, {}
        for _, r in dd.iterrows():
            drivers[r[S.DRIVER]] = DriverDials(
                r["pace_rating"], r["quali_rating"], r["consistency"],
                r["wet_skill"], r["reliability_exposure"])
            dteam[r[S.DRIVER]] = r["team"]
        return cls(name=name, teams=teams, drivers=drivers, driver_team=dteam,
                   debut_prior=derive_debut_prior(results))

    # ── case-insensitive team lookup ──
    def _resolve_team(self, name: str | None) -> str | None:
        """Return the canonical team key matching `name` case-insensitively, or
        None if unknown. Fixes the bug where a hand-entered "McLaren" was
        uppercased to "MCLAREN" and never matched the real "McLaren" default,
        so every known team silently fell back to neutral dials."""
        if name is None:
            return None
        if name in self.teams:
            return name
        low = str(name).lower()
        for k in self.teams:
            if k.lower() == low:
                return k
        return None

    # ── isolation ──
    def copy(self) -> "Scenario":
        """Deep, independent copy. Use this before applying per-request or
        per-session overrides so the shared, data-derived defaults are never
        mutated (see api.main.scenario_predict and the Streamlit panel)."""
        import copy as _copy
        return Scenario(
            name=self.name,
            teams={k: _copy.copy(v) for k, v in self.teams.items()},
            drivers={k: _copy.copy(v) for k, v in self.drivers.items()},
            driver_team=dict(self.driver_team),
            debut_prior=dict(self.debut_prior),
        )

    # ── overrides ──
    def set_team(self, team: str, **kw):
        self.teams.setdefault(team, TeamDials())
        for k, v in kw.items():
            setattr(self.teams[team], k, float(v))

    def set_driver(self, driver: str, **kw):
        self.drivers.setdefault(driver, DriverDials())
        for k, v in kw.items():
            setattr(self.drivers[driver], k, float(v))

    # ── apply ──
    def apply_to_features(self, race_feats: pd.DataFrame) -> pd.DataFrame:
        """Return race features adjusted to reflect this scenario.

        We translate dials into the model's existing feature space so no retrain
        is needed. Concretely, a combined driver+car strength (0..1) is mapped to
        an expected finishing position (1..20), which we write into the form and
        grid-expectation features the model already understands. wet_skill is
        attached for the Monte Carlo layer.
        """
        out = race_feats.copy()
        exp_pos, grid_exp, dnf, wet = [], [], [], []
        for _, row in out.iterrows():
            drv = row[S.DRIVER]
            team = self.driver_team.get(drv, row.get(S.TEAM))
            team_key = self._resolve_team(team)
            tdial = self.teams.get(team_key, TeamDials())
            ddial = self.drivers.get(drv, DriverDials())

            strength = 0.5 * ddial.composite() + 0.5 * tdial.composite()
            # strength 1 -> P1, strength 0 -> ~P20
            pos = 1 + (1 - strength) * 19
            exp_pos.append(pos)
            grid_exp.append(1 + (1 - (0.5 * ddial.quali_rating + 0.5 * tdial.composite())) * 19)
            dnf.append(float(np.clip(ddial.reliability_exposure
                                     + (1 - tdial.reliability) * 0.5, 0.02, 0.4)))
            wet.append(ddial.wet_skill)

        out[S.F_FORM_FINISH] = exp_pos
        out[S.F_CIRCUIT_HIST] = exp_pos
        out[S.F_FORM_GRID] = grid_exp
        out[S.F_GRID] = grid_exp           # scenario grid expectation
        out[S.F_DNF_RATE] = dnf
        out["wet_skill"] = wet
        return out

    # ── persistence ──
    def to_json(self) -> str:
        return json.dumps({
            "name": self.name,
            "teams": {k: asdict(v) for k, v in self.teams.items()},
            "drivers": {k: asdict(v) for k, v in self.drivers.items()},
            "driver_team": self.driver_team,
            "debut_prior": self.debut_prior,
        }, indent=2)

    @classmethod
    def from_json(cls, text: str) -> "Scenario":
        d = json.loads(text)
        return cls(
            name=d["name"],
            teams={k: TeamDials(**v) for k, v in d["teams"].items()},
            drivers={k: DriverDials(**v) for k, v in d["drivers"].items()},
            driver_team=d.get("driver_team", {}),
            debut_prior=d.get("debut_prior", dict(_FALLBACK_DEBUT_PRIOR)),
        )

    # ── manual / hypothetical grid ──
    def features_from_grid(self, grid: list[dict]) -> pd.DataFrame:
        """Build a synthetic race-feature frame from a HAND-ENTERED grid.

        grid: list of {"driver": "VER", "team": "RBR"} in starting-grid order
        (P1 first). Each driver's other features (form, points-to-date, circuit
        history, etc.) are seeded from this scenario's real-data-derived dials
        if the driver is known, or neutral defaults if not — this is for
        exploring hypothetical lineups, not historical races, so there is no
        "true" season/round/circuit context to pull from.

        Returns a DataFrame shaped like build_features() output (same columns
        the trained race model expects), so OrderModel.predict_order() and
        TwoStagePipeline both work on it unmodified.
        """
        rows = []
        for i, entry in enumerate(grid):
            drv = entry["driver"].upper()  # driver codes are uppercase in the data
            raw_team = entry.get("team") or self.driver_team.get(drv, "")
            team_key = self._resolve_team(raw_team)  # case-insensitive; None if new

            driver_known = drv in self.drivers
            team_known = team_key is not None
            ddial = self.drivers.get(drv, DriverDials())
            tdial = self.teams.get(team_key, TeamDials())

            # "no history" = an unknown driver OR a brand-new/renamed team. Without
            # a car with real history we cannot honestly claim a strong finish, so
            # we DO NOT fall back to a neutral mid-grid (which the model reads as a
            # capable car). Instead we use the real 2019-2025 debut prior: how
            # entrants with no history actually finished. This is flagged so the
            # API/UI can label it plainly rather than passing it off as signal.
            no_history = (not driver_known) or (not team_known)

            if no_history:
                # Seed the row to look EXACTLY like a genuine debut row as the
                # model saw it in training: the build_features no-history defaults
                # (form ~ back of grid, zero season points, zero prior experience).
                # These are the FEATURE values the ranker learned to pair with a
                # real debut; the driver then lands near where debut drivers
                # actually finished (self.debut_prior, ~P12 over 2019-2025),
                # NOT the neutral mid-grid it used to be read as a strong car.
                form_finish = NO_HISTORY_FORM_FINISH
                form_grid = NO_HISTORY_FORM_GRID
                circuit_hist = NO_HISTORY_CIRCUIT
                dnf_rate = NO_HISTORY_DNF_RATE
                form_points = NO_HISTORY_FORM_POINTS
                drv_pts_td = 0.0
                team_pts_td = 0.0
                prior_exp = 0.0
                wet = ddial.wet_skill if driver_known else 0.5
            else:
                strength = 0.5 * ddial.composite() + 0.5 * tdial.composite()
                form_finish = 1 + (1 - strength) * 19
                form_grid = float(i + 1)
                circuit_hist = form_finish
                dnf_rate = float(np.clip(
                    ddial.reliability_exposure + (1 - tdial.reliability) * 0.5,
                    0.02, 0.4))
                form_points = ddial.composite() * 18
                drv_pts_td = ddial.composite() * 150
                team_pts_td = tdial.composite() * 200
                prior_exp = 20.0
                wet = ddial.wet_skill

            rows.append({
                S.SEASON: 0, S.ROUND: 0, S.EVENT: "Custom Grid", "race_id": -1,
                S.DRIVER: drv,
                # Preserve the canonical team name when known (don't uppercase it).
                S.TEAM: team_key if team_known else raw_team,
                S.F_GRID: float(i + 1),  # the grid position you actually typed
                S.F_FORM_FINISH: form_finish,
                S.F_FORM_GRID: form_grid,
                S.F_FORM_POINTS: form_points,
                S.F_DNF_RATE: dnf_rate,
                S.F_TEAM_PTS_TD: team_pts_td,
                S.F_DRV_PTS_TD: drv_pts_td,
                S.F_CIRCUIT_HIST: circuit_hist,
                S.F_TEAMMATE_GAP: 0.0,
                S.F_ROUND_NORM: 0.5,
                S.F_PRIOR_EXP: prior_exp,
                "wet_skill": wet,
                # Provenance flag surfaced by the API/UI.
                "no_history": no_history,
            })
        return pd.DataFrame(rows)
