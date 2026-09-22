"""Validate fitted tyre curves against reality on held-out races (item 3).

Two checks, reported with hits AND misses:
  1. stint/stops: does the simulator's FASTEST strategy use the same number of
     pit stops as the field actually used that race?
  2. strategy: does the simulator's fastest compound set match the race winner's
     actual compound set?

Both are run with the DEFAULT curves and the FITTED curves so we can see whether
fitting helped. Curves for a held-out race are fitted ONLY from races strictly
before it (leakage-free).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from f1grid import schema as S
from f1grid.model.tyres import DEFAULT_COMPOUNDS
from f1grid.model.strategy_sim import compare_strategies, StintPlan


def actual_stints(laps: pd.DataFrame, season: int, rnd: int) -> pd.DataFrame:
    """Per-driver stint summary for a race: compounds run and pit-stop count."""
    r = laps[(laps[S.SEASON] == season) & (laps[S.ROUND] == rnd)]
    rows = []
    for drv, g in r.groupby(S.DRIVER):
        stints = g.groupby("stint")["compound"].first().dropna().tolist()
        n_laps = int(g["lap_number"].max()) if not g.empty else 0
        rows.append({"driver": drv, "n_stops": max(len(set(g["stint"].dropna())) - 1, 0),
                     "sequence": stints, "laps": n_laps})
    return pd.DataFrame(rows)


def race_pace(laps: pd.DataFrame, season: int, rnd: int) -> tuple[float, int]:
    """Representative green-lap pace and total laps for a race."""
    from f1grid.model.tyre_fit import filter_representative_laps
    r = laps[(laps[S.SEASON] == season) & (laps[S.ROUND] == rnd)]
    filt, _ = filter_representative_laps(r[~r["compound"].isin(["INTERMEDIATE", "WET"])])
    base = float(filt["lap_time_s"].median()) if not filt.empty else float("nan")
    total = int(r["lap_number"].max()) if not r.empty else 0
    return base, total


def _candidates(total_laps: int) -> dict:
    """1-stop and 2-stop candidate sequences with even-ish splits (dry compounds)."""
    h = total_laps // 2
    t3 = total_laps // 3
    return {
        "1stop_MH": [StintPlan("MEDIUM", h), StintPlan("HARD", total_laps - h)],
        "1stop_HM": [StintPlan("HARD", h), StintPlan("MEDIUM", total_laps - h)],
        "1stop_HH": [StintPlan("HARD", h), StintPlan("HARD", total_laps - h)],
        "2stop_MHH": [StintPlan("MEDIUM", t3), StintPlan("HARD", t3),
                      StintPlan("HARD", total_laps - 2 * t3)],
        "2stop_SMH": [StintPlan("SOFT", t3), StintPlan("MEDIUM", t3),
                      StintPlan("HARD", total_laps - 2 * t3)],
        "2stop_SMM": [StintPlan("SOFT", t3), StintPlan("MEDIUM", t3),
                      StintPlan("MEDIUM", total_laps - 2 * t3)],
    }


def simulate_best(base: float, total_laps: int, compounds: dict) -> dict:
    if not np.isfinite(base) or total_laps < 5:
        return {}
    res = compare_strategies(base, total_laps, _candidates(total_laps),
                             compounds=compounds, n_sims=120, seed=1)
    best = res[0]
    return {"label": best["label"], "n_stops": best["n_stops"],
            "sequence": best["sequence"]}


def validate(laps: pd.DataFrame, results: pd.DataFrame, holdout: list[tuple[int, int]],
             fit_before=True) -> dict:
    """Run both checks on each held-out race with default and fitted curves."""
    from f1grid.model.tyre_fit import fit_curves
    rows = []
    for season, rnd in holdout:
        base, total = race_pace(laps, season, rnd)
        if not np.isfinite(base) or total < 5:
            continue
        act = actual_stints(laps, season, rnd)
        classified = results[(results[S.SEASON] == season) & (results[S.ROUND] == rnd) &
                             (results[S.DNF] == 0)]
        if act.empty or classified.empty:
            continue
        # field's typical stops (median among drivers who ran) and winner's set
        modal_stops = int(round(act["n_stops"].median()))
        winner = classified.sort_values(S.FINISH)[S.DRIVER].iloc[0]
        wrow = act[act["driver"] == winner]
        winner_set = set(wrow["sequence"].iloc[0]) if not wrow.empty else set()

        default_best = simulate_best(base, total, DEFAULT_COMPOUNDS)
        fit = fit_curves(laps, before=(season, rnd) if fit_before else None)
        fitted_best = simulate_best(base, total, fit.compounds())

        rows.append({
            "season": season, "round": rnd,
            "actual_modal_stops": modal_stops,
            "winner": winner, "winner_set": ",".join(sorted(winner_set)),
            "default_stops": default_best.get("n_stops"),
            "default_seq": ",".join(default_best.get("sequence", [])),
            "fitted_stops": fitted_best.get("n_stops"),
            "fitted_seq": ",".join(fitted_best.get("sequence", [])),
            "default_stops_hit": default_best.get("n_stops") == modal_stops,
            "fitted_stops_hit": fitted_best.get("n_stops") == modal_stops,
            "default_set_hit": bool(winner_set) and
                set(default_best.get("sequence", [])) == winner_set,
            "fitted_set_hit": bool(winner_set) and
                set(fitted_best.get("sequence", [])) == winner_set,
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return {"races": 0}
    return {
        "races": len(df),
        "default_stops_hit_rate": round(df["default_stops_hit"].mean(), 3),
        "fitted_stops_hit_rate": round(df["fitted_stops_hit"].mean(), 3),
        "default_set_hit_rate": round(df["default_set_hit"].mean(), 3),
        "fitted_set_hit_rate": round(df["fitted_set_hit"].mean(), 3),
        "detail": df,
    }
