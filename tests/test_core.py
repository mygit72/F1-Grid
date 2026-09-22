"""Core test suite. Run with: pytest tests/ -v

Uses tests/synthetic.py (never the real path) so tests run anywhere, no network
or pyarrow required.
"""
from __future__ import annotations

import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from f1grid import schema as S
from f1grid.features.build import build_features, assert_no_leakage
from f1grid.model.order_model import OrderModel
from f1grid.model.quali_model import QualiModel
from f1grid.model.pipeline import TwoStagePipeline
from f1grid.model.evaluate import walk_forward, summarize
from f1grid.model.montecarlo import monte_carlo_outcomes
from f1grid.model.strategy_sim import simulate_strategy, compare_strategies, StintPlan
from f1grid.model.panel import Scenario
from f1grid.store import predictions as PS
from f1grid.score import scorer as SC
from tests.synthetic import make_synthetic


@pytest.fixture(scope="module")
def results():
    return make_synthetic(seasons=(2023, 2024, 2025), rounds_per_season=10, seed=7)


@pytest.fixture(scope="module")
def feats(results):
    return build_features(results)


# ── feature / leakage tests ────────────────────────────────────────────────

def test_features_have_no_nulls_in_key_columns(feats):
    for col in [S.F_GRID, S.FINISH, S.DRIVER, S.SEASON, S.ROUND]:
        assert feats[col].isna().sum() == 0


def test_no_leakage_self_check(results, feats):
    # Should not raise.
    assert_no_leakage(results, feats)


def test_feature_builder_never_reads_current_finish_directly():
    """Static guard: build_features's per-row dict must not pull row[S.FINISH]
    for anything except the label slot itself."""
    import inspect
    from f1grid.features import build as build_mod
    src = inspect.getsource(build_mod.build_features)
    # Only one legitimate read of row[FINISH]: assigning the label.
    occurrences = src.count(f"row[S.FINISH]")
    assert occurrences == 1, (
        f"Expected exactly 1 read of row[S.FINISH] (the label assignment), "
        f"found {occurrences}. A new feature may be leaking the outcome."
    )


def test_first_race_has_zero_prior_experience(feats):
    first_race_id = feats["race_id"].min()
    first = feats[feats["race_id"] == first_race_id]
    assert (first[S.F_PRIOR_EXP] == 0).all()


# ── model tests ───────────────────────────────────────────────────────────

def test_order_model_predicts_all_drivers(feats):
    train = feats[feats["race_id"] < feats["race_id"].max()]
    test = feats[feats["race_id"] == feats["race_id"].max()]
    model = OrderModel().fit(train)
    order = model.predict_order(test)
    assert set(order[S.DRIVER]) == set(test[S.DRIVER])
    assert sorted(order["predicted_position"]) == list(range(1, len(test) + 1))


def test_quali_model_excludes_grid_feature():
    from f1grid.model.quali_model import QUALI_FEATURES
    assert S.F_GRID not in QUALI_FEATURES


def test_two_stage_pipeline_runs_predicted_and_real_grid(feats):
    train = feats[feats["race_id"] < feats["race_id"].max()]
    test = feats[feats["race_id"] == feats["race_id"].max()]
    pipe = TwoStagePipeline().fit(train)
    a = pipe.predict_weekend(test, use_real_grid=True)
    b = pipe.predict_weekend(test, use_real_grid=False)
    assert set(a[S.DRIVER]) == set(b[S.DRIVER]) == set(test[S.DRIVER])


def test_walk_forward_reports_baseline(feats):
    report = walk_forward(feats, eval_seasons=(2025,))
    summary = summarize(report)
    assert set(summary["system"]) == {"F1Grid model", "Grid-order baseline"}
    assert (summary["races"] > 0).all()


# ── monte carlo / rain tests ─────────────────────────────────────────────

def test_monte_carlo_probabilities_sum_reasonably(feats):
    train = feats[feats["race_id"] < feats["race_id"].max()]
    test = feats[feats["race_id"] == feats["race_id"].max()].copy()
    model = OrderModel().fit(train)
    order = model.predict_order(test)
    order["wet_skill"] = 0.5
    out = monte_carlo_outcomes(order, rain_prob=0.0, n_sims=1000)
    assert np.isclose(out["win_prob"].sum(), 1.0, atol=0.02)
    assert (out["podium_prob"] <= 1.0).all()
    assert (out["points_prob"] >= out["podium_prob"]).all()


def test_rain_increases_variance_effect():
    """A driver with high wet_skill should gain relative win share as rain rises."""
    df = pd.DataFrame({
        S.DRIVER: ["A", "B", "C"],
        S.TEAM: ["T1", "T2", "T3"],
        "predicted_position": [1, 2, 3],
        "model_score": [3.0, 2.0, 1.0],
        S.F_DNF_RATE: [0.05, 0.05, 0.05],
        "wet_skill": [0.2, 0.95, 0.5],
    })
    dry = monte_carlo_outcomes(df, rain_prob=0.0, n_sims=4000, seed=1)
    wet = monte_carlo_outcomes(df, rain_prob=0.9, n_sims=4000, seed=1)
    b_dry = dry.loc[dry[S.DRIVER] == "B", "win_prob"].iloc[0]
    b_wet = wet.loc[wet[S.DRIVER] == "B", "win_prob"].iloc[0]
    assert b_wet > b_dry, "High wet-skill driver should gain win share as rain rises"


# ── strategy simulator tests ─────────────────────────────────────────────

def test_stops_emerge_from_compound_sequence_length():
    seq = [StintPlan("SOFT", 14), StintPlan("MEDIUM", 22), StintPlan("HARD", 21)]
    r = simulate_strategy(90.0, 57, seq)
    assert r["n_stops"] == 2, "n_stops must equal len(sequence) - 1, never a manual input"


def test_overlong_soft_stint_is_penalized():
    one_stop = simulate_strategy(90.0, 57, [StintPlan("MEDIUM", 26), StintPlan("HARD", 31)])
    forced_soft = simulate_strategy(90.0, 57, [StintPlan("SOFT", 57)])
    assert forced_soft["total_time"] > one_stop["total_time"] + 100, (
        "Running one compound far past its life must be slower due to the cliff model"
    )


def test_compare_strategies_ranks_and_reports_gap():
    candidates = {
        "1-stop": [StintPlan("MEDIUM", 26), StintPlan("HARD", 31)],
        "bad-all-soft": [StintPlan("SOFT", 57)],
    }
    res = compare_strategies(90.0, 57, candidates, n_sims=100)
    assert res[0]["label"] == "1-stop"
    assert res[0]["gap_to_best"] == 0.0
    assert res[1]["gap_to_best"] > 0


def test_rain_slows_all_strategies():
    seq = [StintPlan("MEDIUM", 26), StintPlan("HARD", 31)]
    dry = simulate_strategy(90.0, 57, seq, rain_prob=0.0, rng=np.random.default_rng(0))
    wet = simulate_strategy(90.0, 57, seq, rain_prob=0.8, rng=np.random.default_rng(0))
    assert wet["total_time"] > dry["total_time"]


def test_slicks_lose_to_wets_in_heavy_rain():
    """Regression test for a real bug: rain used to apply a FLAT penalty to
    every compound equally, so it never changed which strategy ranked best —
    slicks would still 'win' even at 100% rain. Compound choice must actually
    matter once conditions are wet."""
    candidates = {
        "slicks": [StintPlan("SOFT", 14), StintPlan("MEDIUM", 43)],
        "wets": [StintPlan("INTER", 20), StintPlan("WET", 37)],
    }
    dry = compare_strategies(90.0, 57, candidates, rain_prob=0.0, n_sims=200)
    wet = compare_strategies(90.0, 57, candidates, rain_prob=1.0, n_sims=200)

    assert dry[0]["label"] == "slicks", "Slicks should win in the dry"
    assert wet[0]["label"] == "wets", "Wet tyres must win once rain_prob=1.0 — this is the bug we fixed"
    # The wet penalty on slicks must be severe, not a token amount.
    slicks_wet_time = next(r for r in wet if r["label"] == "slicks")["mean_time"]
    wets_wet_time = next(r for r in wet if r["label"] == "wets")["mean_time"]
    assert slicks_wet_time > wets_wet_time + 500, (
        "Slicks in full wet should be drastically slower than proper wet tyres"
    )


# ── 2026 scenario panel tests ──────────────────────────────────────────

def test_scenario_defaults_derived_from_data(results):
    sc = Scenario.from_results(results)
    assert len(sc.teams) > 0 and len(sc.drivers) > 0
    # aero/PU not observable -> must default neutral
    any_team = next(iter(sc.teams.values()))
    assert any_team.aero_efficiency == 0.5
    assert any_team.power_unit == 0.5


def test_scenario_override_changes_outcome(results, feats):
    sc = Scenario.from_results(results)
    race_id = feats["race_id"].max()
    race = feats[feats["race_id"] == race_id].copy()
    train = feats[feats["race_id"] < race_id]
    model = OrderModel().fit(train)

    base_order = model.predict_order(sc.apply_to_features(race))
    weakest_team = min(sc.teams, key=lambda t: sc.teams[t].car_pace)
    sc.set_team(weakest_team, car_pace=0.99, power_unit=0.99, aero_efficiency=0.99)
    boosted_order = model.predict_order(sc.apply_to_features(race))

    drivers_on_team = [d for d, t in sc.driver_team.items() if t == weakest_team]
    if drivers_on_team:
        b_pos = base_order.set_index(S.DRIVER).loc[drivers_on_team[0], "predicted_position"]
        new_pos = boosted_order.set_index(S.DRIVER).loc[drivers_on_team[0], "predicted_position"]
        assert new_pos <= b_pos, "Boosting a team's dials should not worsen its driver's position"


def test_scenario_json_roundtrip(results):
    sc = Scenario.from_results(results)
    sc2 = Scenario.from_json(sc.to_json())
    assert sc2.teams.keys() == sc.teams.keys()
    assert sc2.drivers.keys() == sc.drivers.keys()


def test_manual_grid_prediction_differs_from_input(results, feats):
    """Your-grid vs predicted-finish should genuinely differ when a known
    strong driver starts at the back and a known weak driver starts on pole —
    otherwise the model would just be echoing the input grid back."""
    sc = Scenario.from_results(results)
    strong = max(sc.drivers, key=lambda d: sc.drivers[d].pace_rating)
    weak = min(sc.drivers, key=lambda d: sc.drivers[d].pace_rating)
    others = [d for d in sc.drivers if d not in (strong, weak)][:6]

    grid = (
        [{"driver": weak, "team": sc.driver_team.get(weak, "UNK")}]
        + [{"driver": d, "team": sc.driver_team.get(d, "UNK")} for d in others]
        + [{"driver": strong, "team": sc.driver_team.get(strong, "UNK")}]
    )
    feat_rows = sc.features_from_grid(grid)
    assert len(feat_rows) == len(grid)
    assert list(feat_rows[S.F_GRID]) == [float(i + 1) for i in range(len(grid))]

    train = feats[feats["race_id"] < feats["race_id"].max()]
    model = OrderModel().fit(train)
    order = model.predict_order(feat_rows).sort_values("predicted_position")

    input_positions = {g["driver"]: i + 1 for i, g in enumerate(grid)}
    output_positions = {
        r[S.DRIVER]: r["predicted_position"] for _, r in order.iterrows()
    }
    assert input_positions != output_positions, (
        "Predicted finish must not simply echo the manually entered grid"
    )


def test_manual_grid_unknown_driver_gets_debut_prior_not_neutral(results):
    """Item 3: an unknown driver / new team is seeded like a genuine DEBUT row
    (back-of-grid form, zero season points, flagged no_history), NOT a neutral
    mid-grid the ranker would misread as a capable car."""
    from f1grid.features.build import NO_HISTORY_FORM_FINISH
    sc = Scenario.from_results(results)
    grid = [{"driver": "ZZZ", "team": "GHOST"}, {"driver": "YYY", "team": "GHOST"}]
    feat_rows = sc.features_from_grid(grid)
    assert len(feat_rows) == 2
    assert feat_rows["no_history"].all()
    assert feat_rows[S.F_FORM_FINISH].iloc[0] == NO_HISTORY_FORM_FINISH
    assert feat_rows[S.F_DRV_PTS_TD].iloc[0] == 0.0


# ── prediction store / scorer tests ───────────────────────────────────

@pytest.fixture()
def tmp_store():
    tmp = Path(tempfile.mkdtemp())
    pred_dir = tmp / "pred"
    pred_dir.mkdir()
    yield pred_dir, tmp / "scorecard.csv"
    shutil.rmtree(tmp)


# A future race start so these store tests are valid PRE-RACE public writes,
# independent of the real schedule artifact.
_FUTURE = lambda *_: datetime(2099, 6, 1, tzinfo=timezone.utc)


def test_prediction_store_is_immutable(tmp_store, feats):
    pred_dir, _ = tmp_store
    race = feats[feats["race_id"] == feats["race_id"].max()].copy()
    race["predicted_position"] = range(1, len(race) + 1)
    path1 = PS.save_prediction(2099, 1, "Test GP", race, data_cutoff="2098 R20",
                               pred_dir=pred_dir, schedule_lookup=_FUTURE)
    assert Path(path1).exists()
    # A second save for the same race must not overwrite the first.
    path2 = PS.save_prediction(2099, 1, "Test GP", race, data_cutoff="2098 R20",
                               pred_dir=pred_dir, schedule_lookup=_FUTURE)
    assert Path(path1) != Path(path2)
    assert Path(path1).exists() and Path(path2).exists()


def test_scorer_grades_against_real_result(tmp_store, results, feats):
    pred_dir, scorecard = tmp_store
    race_id = feats["race_id"].max()
    season = int(feats[feats["race_id"] == race_id][S.SEASON].iloc[0])
    rnd = int(feats[feats["race_id"] == race_id][S.ROUND].iloc[0])

    train = feats[feats["race_id"] < race_id]
    test = feats[feats["race_id"] == race_id].copy()
    model = OrderModel().fit(train)
    order = model.predict_order(test)

    PS.save_prediction(season, rnd, "Test Event", order, data_cutoff="prior",
                       pred_dir=pred_dir, schedule_lookup=_FUTURE)
    row = SC.score_race(season, rnd, results, scorecard=scorecard, pred_dir=pred_dir)
    assert row is not None
    assert 0.0 <= row["podium_acc"] <= 1.0
    assert "baseline_spearman" in row

    tr = SC.track_record(scorecard=scorecard)
    assert "cum_top1" in tr.columns


def test_scorer_returns_none_without_prediction(tmp_store, results):
    pred_dir, scorecard = tmp_store
    row = SC.score_race(1900, 1, results, scorecard=scorecard, pred_dir=pred_dir)
    assert row is None
