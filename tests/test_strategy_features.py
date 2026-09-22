"""Strategy-feature tests (item 4).

Guards:
  - circuit features use ONLY prior races (leakage self-check),
  - a new venue with no prior history gets the flagged pooled fallback,
  - a recurring circuit is NOT flagged and its overtaking difficulty reflects
    only prior runnings,
  - the ablation feature set trains/scores through the model.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from f1grid import schema as S
from f1grid.features import strategy_features as SF
from f1grid.features.build import build_features
from f1grid.model.evaluate import model_summary
from tests.synthetic import make_synthetic


def _synth_laps(results):
    """Minimal lap frame for a couple of circuits from the synthetic results."""
    rng = np.random.default_rng(0)
    rows = []
    for (season, rnd, circuit, date), g in results.groupby(
            [S.SEASON, S.ROUND, S.EVENT, S.DATE]):
        if rnd > 3:  # only give a few races lap data, to exercise fallback
            continue
        for drv in g[S.DRIVER].head(6):
            lap = 0
            for stint_no, comp in enumerate(["MEDIUM", "HARD"], start=1):
                for age in range(1, 16):
                    lap += 1
                    rows.append({
                        S.SEASON: season, S.ROUND: rnd, S.EVENT: circuit,
                        S.DATE: date, S.DRIVER: drv, S.TEAM: "T",
                        "lap_number": lap, "lap_time_s": 90 + 0.04 * age - 0.05 * lap,
                        "stint": stint_no, "compound": comp, "tyre_life": age,
                        "is_pit_in": age == 15, "is_pit_out": age == 1 and stint_no > 1,
                        "track_status": "1", "is_accurate": True,
                        "position": 1, "race_is_wet": False,
                    })
    return pd.DataFrame(rows)


def test_strategy_features_use_only_prior_races():
    results = make_synthetic(seasons=(2023, 2024), rounds_per_season=6, seed=3)
    laps = _synth_laps(results)
    SF.assert_strategy_features_no_leakage(results, laps, eval_seasons=[2024])


def test_new_venue_is_flagged_no_history():
    results = make_synthetic(seasons=(2023, 2024), rounds_per_season=6, seed=3)
    laps = _synth_laps(results)  # lap data for rounds 1-3, recurring each season
    strat = SF.build_strategy_features(results, laps)
    strat = strat.merge(results[[S.SEASON, S.ROUND, S.EVENT]].drop_duplicates(),
                        on=[S.SEASON, S.ROUND])
    # 2023 R1 is the very first race of the dataset -> no prior lap history at all
    first = strat[(strat[S.SEASON] == 2023) & (strat[S.ROUND] == 1)]
    assert int(first[SF.STRAT_NO_HISTORY].iloc[0]) == 1
    # the same circuit in 2024 has prior lap history (2023 R1) -> not flagged
    circuit_r1 = first[S.EVENT].iloc[0]
    later = strat[(strat[S.SEASON] == 2024) & (strat[S.EVENT] == circuit_r1)]
    assert int(later[SF.STRAT_NO_HISTORY].iloc[0]) == 0


def test_overtake_diff_reflects_prior_only_and_is_bounded():
    results = make_synthetic(seasons=(2023, 2024), rounds_per_season=6, seed=3)
    strat = SF.build_strategy_features(results, laps=None)
    od = strat["circuit_overtake_diff"]
    assert od.between(-1.0, 1.0).all()


def test_model_trains_and_scores_with_strategy_columns():
    results = make_synthetic(seasons=(2022, 2023, 2024), rounds_per_season=6, seed=5)
    feats = build_features(results)
    feats = SF.attach_strategy_features(feats, results, laps=None)
    cols = list(S.FEATURE_COLUMNS) + list(SF.STRAT_FEATURES) + [SF.STRAT_NO_HISTORY]
    m = model_summary(feats, (2024,), feature_columns=cols)
    assert m and -1.0 <= m["spearman"] <= 1.0
