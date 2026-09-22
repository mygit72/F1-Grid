"""Pre-qualifying baseline tests (item 2).

Guards three contracts:
  1. the baselines use ONLY prior races (leakage self-check),
  2. a prediction published BEFORE qualifying is graded against the
     pre-qualifying baselines,
  3. a prediction published AFTER qualifying is graded against grid order.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from f1grid import schema as S
from f1grid.model import baselines as B
from f1grid.store import predictions as PS
from f1grid.score import scorer as SC
from tests.synthetic import make_synthetic

UTC = timezone.utc


@pytest.fixture(scope="module")
def results():
    # A few seasons so every eval race has prior history to lean on.
    return make_synthetic(seasons=(2023, 2024, 2025), rounds_per_season=10, seed=7)


# ── 1. leakage: baselines never read the race's own result ──────────────────

def test_baselines_use_only_prior_races(results):
    # Raises if any baseline order for a race changes when only that race's own
    # finishing positions are corrupted.
    B.assert_baselines_no_leakage(results, eval_seasons=[2025])


def test_previous_race_order_equals_prior_race_finish(results):
    prev = B.previous_race_order(results, 2025, 5)
    prior = (results[(results[S.SEASON] == 2025) & (results[S.ROUND] == 4)]
             .sort_values(S.FINISH))
    assert prev[S.DRIVER].tolist() == prior[S.DRIVER].tolist()


def test_previous_race_debutant_is_ranked_last(results):
    # Inject a brand-new driver into 2025 R5 who never appeared before.
    r = results.copy()
    r5 = r[(r[S.SEASON] == 2025) & (r[S.ROUND] == 5)]
    debut = r5.iloc[[0]].copy()
    debut[S.DRIVER] = "ZZZ"
    debut[S.FINISH] = 5
    r = pd.concat([r, debut], ignore_index=True)
    order = B.previous_race_order(r, 2025, 5)
    assert order[S.DRIVER].iloc[-1] == "ZZZ"  # no prior race -> very back


def test_championship_standings_orders_by_points(results):
    order = B.championship_standings_order(results, 2025, 6)
    # Reconstruct season-to-date points through round 5 independently.
    hist = results[(results[S.SEASON] == 2025) & (results[S.ROUND] < 6)].copy()
    hist["pts"] = hist[S.FINISH].apply(S.points_for)
    pts = hist.groupby(S.DRIVER)["pts"].sum()
    leader = pts.idxmax()
    assert order[S.DRIVER].iloc[0] == leader


# ── 2 & 3. scorer selects the baseline that matches when the pick was made ──

def _save_and_score(results, tmp_path, *, pre_qualifying: bool):
    season, rnd = 2025, 8
    made = datetime(2025, 1, 1, tzinfo=UTC)
    race_start = lambda *_: made + timedelta(days=3)          # future -> valid public
    quali = (made + timedelta(days=1)) if pre_qualifying else (made - timedelta(days=1))
    quali_lookup = lambda *_: quali

    race = results[(results[S.SEASON] == season) & (results[S.ROUND] == rnd)].copy()
    order = race.sort_values(S.GRID)[[S.DRIVER, S.TEAM]].reset_index(drop=True)
    order["predicted_position"] = range(1, len(order) + 1)

    pred_dir = tmp_path / "preds"
    pred_dir.mkdir()
    PS.save_prediction(season, rnd, "Synthetic GP", order, data_cutoff="prior",
                       pred_dir=pred_dir, now_utc=made,
                       schedule_lookup=race_start, quali_lookup=quali_lookup)
    row = SC.score_race(season, rnd, results,
                        scorecard=tmp_path / "sc.csv", pred_dir=pred_dir)
    return row


def test_pre_qualifying_prediction_scored_against_prequali_baselines(results, tmp_path):
    row = _save_and_score(results, tmp_path, pre_qualifying=True)
    assert row is not None
    assert row["baseline_used"] == "pre_qualifying"
    assert row["baseline_champ_spearman"] is not None
    assert row["baseline_prevrace_spearman"] is not None


def test_post_qualifying_prediction_scored_against_grid_order(results, tmp_path):
    row = _save_and_score(results, tmp_path, pre_qualifying=False)
    assert row is not None
    assert row["baseline_used"] == "grid_order"
    assert row["baseline_champ_spearman"] is None
