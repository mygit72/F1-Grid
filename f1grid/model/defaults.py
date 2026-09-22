"""Derive real-data DEFAULTS for the 2026 input panel.

Everything the panel exposes defaults to a value computed from the historical
results parquet, so "deep and realistic" means real defaults you may override —
not a wall of guesses. Override values live in a Scenario (panel.py); these are
the priors they start from.

Driver skills derived:
  - pace_rating: from recent average finishing position (better -> higher).
  - quali_rating: from recent average grid position.
  - consistency: inverse of finish-position variance.
  - wet_skill: overperformance in wet races vs that driver's dry baseline.
  - reliability_exposure: driver DNF rate (driver+car combined historically).
Team ratings derived:
  - car_pace: team mean finishing position (recent), normalized.
  - reliability: 1 - team DNF rate.
Aero/PU are not directly observable from results, so they default to NEUTRAL and
are explicit override-only dials (clearly the assumption surface).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from f1grid import schema as S


def _norm_position_to_rating(avg_pos: float, field: float = 20.0) -> float:
    """Map an average finishing/grid position to a 0..1 rating (P1 -> ~1)."""
    return float(np.clip((field - avg_pos) / (field - 1), 0.0, 1.0))


def derive_driver_defaults(results: pd.DataFrame, recent_seasons: int = 2,
                           wet_events: list[str] | None = None) -> pd.DataFrame:
    df = results.copy()
    max_season = df[S.SEASON].max()
    recent = df[df[S.SEASON] > max_season - recent_seasons]

    rows = []
    for drv, g in recent.groupby(S.DRIVER):
        finished = g[g[S.DNF] == 0]
        avg_fin = finished[S.FINISH].mean() if len(finished) else 18.0
        avg_grid = g[S.GRID].mean()
        var_fin = finished[S.FINISH].var() if len(finished) > 1 else 25.0
        dnf_rate = g[S.DNF].mean()

        wet_skill = 0.5
        if wet_events:
            wet = finished[finished[S.EVENT].isin(wet_events)]
            if len(wet) >= 2:
                # overperformance: dry baseline finish minus wet finish, scaled
                delta = avg_fin - wet[S.FINISH].mean()
                wet_skill = float(np.clip(0.5 + delta / 20.0, 0.0, 1.0))

        rows.append({
            S.DRIVER: drv,
            "team": g[S.TEAM].iloc[-1],
            "pace_rating": round(_norm_position_to_rating(avg_fin), 3),
            "quali_rating": round(_norm_position_to_rating(avg_grid), 3),
            "consistency": round(float(np.clip(1.0 - var_fin / 60.0, 0.0, 1.0)), 3),
            "wet_skill": round(wet_skill, 3),
            "reliability_exposure": round(float(dnf_rate), 3),
        })
    return pd.DataFrame(rows).sort_values("pace_rating", ascending=False).reset_index(drop=True)


def derive_debut_prior(results: pd.DataFrame) -> dict:
    """Real-data prior for an entrant with NO history (a debut driver or a brand
    new / renamed team) in the 2019-2025 results.

    A driver's or team's *first* appearance in the dataset is a genuine "no
    history" row. We take every driver's earliest race and measure how they
    actually finished. This is the honest prior for an unknown grid entry -
    demonstrably worse than the neutral mid-grid the panel used to assume, and
    it carries the real debut DNF exposure too.

    Returns expected_finish (mean finishing position incl. DNF sentinel, the
    same quantity the form feature encodes), classified_finish (finishers only),
    dnf_rate, and n_debuts.
    """
    df = results.copy()
    df[S.DATE] = pd.to_datetime(df[S.DATE])
    df = df.sort_values([S.DATE, S.SEASON, S.ROUND])
    firsts = df.drop_duplicates(subset=[S.DRIVER], keep="first")
    if firsts.empty:
        return {"expected_finish": 15.0, "classified_finish": 12.0,
                "dnf_rate": 0.15, "n_debuts": 0,
                "season_min": None, "season_max": None}
    finishers = firsts[firsts[S.DNF] == 0]
    exp_finish = float(firsts[S.FINISH].mean())
    classified = (float(finishers[S.FINISH].mean())
                  if len(finishers) else exp_finish)
    return {
        "expected_finish": round(exp_finish, 3),
        "classified_finish": round(classified, 3),
        "dnf_rate": round(float(firsts[S.DNF].mean()), 3),
        "n_debuts": int(len(firsts)),
        "season_min": int(df[S.SEASON].min()),
        "season_max": int(df[S.SEASON].max()),
    }


def derive_team_defaults(results: pd.DataFrame, recent_seasons: int = 2) -> pd.DataFrame:
    df = results.copy()
    max_season = df[S.SEASON].max()
    recent = df[df[S.SEASON] > max_season - recent_seasons]

    rows = []
    for team, g in recent.groupby(S.TEAM):
        finished = g[g[S.DNF] == 0]
        avg_fin = finished[S.FINISH].mean() if len(finished) else 15.0
        dnf_rate = g[S.DNF].mean()
        rows.append({
            "team": team,
            "car_pace": round(_norm_position_to_rating(avg_fin), 3),
            "reliability": round(float(np.clip(1.0 - dnf_rate, 0.0, 1.0)), 3),
            # Not observable from results -> neutral, override-only:
            "aero_efficiency": 0.5,
            "power_unit": 0.5,
        })
    return pd.DataFrame(rows).sort_values("car_pace", ascending=False).reset_index(drop=True)
