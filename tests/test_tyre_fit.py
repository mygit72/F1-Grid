"""Tyre-degradation fitting tests (item 3).

Guards:
  - the documented filters remove exactly the non-representative laps,
  - the fuel effect is ESTIMATED from the data (recovered on clean synthetic data),
  - degradation ordering is recovered when identification is clean,
  - the cliff stays a labelled default (never invented),
  - leakage: fitting with `before=` never uses the target race or later races,
  - compare_strategies still accepts default compounds (rain regression untouched).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from f1grid import schema as S
from f1grid.model import tyre_fit as TF


def _synth_laps(seed=0):
    """Clean synthetic stints with KNOWN fuel + per-compound degradation and real
    cross-stint variation (two stints per driver), so fuel and deg are identifiable.
    True: fuel=0.05 s/lap improvement, deg SOFT=0.08 > MEDIUM=0.05 > HARD=0.03."""
    rng = np.random.default_rng(seed)
    true_deg = {"SOFT": 0.08, "MEDIUM": 0.05, "HARD": 0.03}
    fuel = 0.05
    rows = []
    for (season, rnd, event, date, base) in [
        (2020, 1, "A GP", "2020-03-01", 90.0),
        (2020, 2, "B GP", "2020-03-15", 95.0),
    ]:
        for drv in range(8):
            # two stints, compounds chosen so each compound gets many laps/stints
            seq = [["SOFT", "HARD"], ["MEDIUM", "HARD"], ["HARD", "MEDIUM"],
                   ["SOFT", "MEDIUM"]][drv % 4]
            lap = 0
            for stint_no, comp in enumerate(seq, start=1):
                for age in range(1, 21):
                    lap += 1
                    lt = (base + true_deg[comp] * age - fuel * lap
                          + rng.normal(0, 0.05))
                    rows.append({
                        S.SEASON: season, S.ROUND: rnd, S.EVENT: event,
                        S.DATE: pd.Timestamp(date), S.DRIVER: f"D{drv}",
                        S.TEAM: "T", "lap_number": lap, "lap_time_s": lt,
                        "stint": stint_no, "compound": comp, "tyre_life": age,
                        "is_pit_in": age == 20, "is_pit_out": age == 1 and stint_no > 1,
                        "track_status": "1", "is_accurate": True,
                        "position": drv + 1, "race_is_wet": False,
                    })
    return pd.DataFrame(rows)


def test_filters_remove_nonrepresentative_laps():
    df = _synth_laps()
    filt, rep = TF.filter_representative_laps(df)
    assert rep.total == len(df)
    # lap 1, pit-in and pit-out laps must all be gone
    assert (filt["lap_number"] >= TF.MIN_LAP_NUMBER).all()
    assert not filt["is_pit_in"].any()
    assert not filt["is_pit_out"].any()
    assert "lap_1" in rep.dropped and "pit_in_lap" in rep.dropped


def test_filters_drop_safety_car_laps():
    df = _synth_laps()
    # mark 10 mid-stint green laps (lap>=3, not pit) as safety car
    victim = df[(df["lap_number"].between(3, 12)) & (df[S.DRIVER] == "D0")].index[:10]
    assert len(victim) == 10
    df.loc[victim, "track_status"] = "4"  # safety car
    filt, rep = TF.filter_representative_laps(df)
    assert rep.dropped.get("safety_car_vsc_yellow", 0) >= 10
    assert (filt["track_status"] == "1").all()


def test_fuel_is_estimated_from_data_not_constant():
    fit = TF.fit_curves(_synth_laps())
    # recovered fuel near the true 0.05, and NOT the hardcoded prior default 0.045
    assert 0.03 < fit.fuel_effect_per_lap < 0.07
    assert "estimated from data" in fit.fuel_source


def test_degradation_ordering_recovered_on_clean_data():
    fit = TF.fit_curves(_synth_laps())
    soft = fit.pooled["SOFT"]["deg_rate"]
    med = fit.pooled["MEDIUM"]["deg_rate"]
    hard = fit.pooled["HARD"]["deg_rate"]
    assert soft > med > hard  # true ordering is recoverable when identified
    # every curve reports its stint and lap counts
    for c in ("SOFT", "MEDIUM", "HARD"):
        assert fit.pooled[c]["n_stints"] > 0 and fit.pooled[c]["n_laps"] > 0


def test_cliff_is_labelled_default_never_invented():
    fit = TF.fit_curves(_synth_laps())
    for c in ("SOFT", "MEDIUM", "HARD"):
        assert fit.pooled[c]["cliff_is_default"] is True
        from f1grid.model.tyres import DEFAULT_COMPOUNDS
        assert fit.pooled[c]["cliff_lap"] == DEFAULT_COMPOUNDS[c].cliff_lap


def test_fit_before_excludes_target_and_later_races():
    df = _synth_laps()
    # fitting before the first race uses no laps at all
    empty = TF.fit_curves(df, before=(2020, 1))
    assert empty.n_events == 0
    # fitting before the second race uses only the first
    one = TF.fit_curves(df, before=(2020, 2))
    assert one.n_events == 1


def test_wet_kept_as_labelled_default():
    fit = TF.fit_curves(_synth_laps())
    for c in ("INTERMEDIATE", "WET"):
        assert fit.wet[c]["status"] == "labelled_default"


def test_compare_strategies_accepts_fitted_compounds():
    from f1grid.model.strategy_sim import compare_strategies, StintPlan
    from f1grid.model.tyres import DEFAULT_COMPOUNDS
    cand = {"a": [StintPlan("MEDIUM", 30), StintPlan("HARD", 27)]}
    res = compare_strategies(90.0, 57, cand, compounds=DEFAULT_COMPOUNDS, n_sims=20)
    assert res and "mean_time" in res[0]
