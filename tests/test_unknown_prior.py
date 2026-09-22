"""Unknown-driver / new-team prior regression tests (item 3).

Two root causes are guarded here:

1. Team-name case mismatch. features_from_grid used to uppercase the entered
   team ("McLaren" -> "MCLAREN"), which never matched the real, mixed-case team
   key, so every KNOWN team silently fell back to neutral dials. Teams are now
   matched case-insensitively.

2. Unknown entrants read as strong. An unknown driver / brand-new team used to
   get neutral 0.5 dials -> ~P10 form + fabricated points-to-date, which the
   ranker reads as a capable midfield car. An unknown entry is now seeded to look
   exactly like a genuine DEBUT row as the model saw it in training (the
   build_features no-history defaults: back-of-grid form, zero season points,
   zero prior experience), so it lands near where debut drivers actually finished
   (Scenario.debut_prior, derived from real 2019-2025 results), not near the front.
"""
from __future__ import annotations

import pandas as pd
import pytest

from f1grid import schema as S
from f1grid.features.build import (
    build_features, NO_HISTORY_FORM_FINISH, NO_HISTORY_FORM_POINTS, NO_HISTORY_CIRCUIT,
)
from f1grid.model.defaults import derive_debut_prior
from f1grid.model.order_model import OrderModel
from f1grid.model.panel import Scenario
from tests.synthetic import make_synthetic


@pytest.fixture(scope="module")
def results():
    return make_synthetic(seasons=(2019, 2020, 2021, 2022, 2023, 2024, 2025),
                          rounds_per_season=12, seed=11)


@pytest.fixture(scope="module")
def feats(results):
    return build_features(results)


@pytest.fixture(scope="module")
def model(feats):
    return OrderModel().fit(feats)


# ── root cause 1: team case-insensitivity ──────────────────────────────────

def test_known_team_resolves_case_insensitively(results):
    sc = Scenario.from_results(results)
    real_team = next(iter(sc.teams))          # canonical key, e.g. "FER"
    drv = next(d for d, t in sc.driver_team.items() if t == real_team)

    # Enter the team in a different case than stored.
    weird = real_team.swapcase()
    rows = sc.features_from_grid([{"driver": drv, "team": weird}])
    assert rows["no_history"].iloc[0] == False  # noqa: E712  -> resolved as known
    assert rows[S.TEAM].iloc[0] == real_team     # canonical name preserved

    # And it uses the REAL team dials, not neutral: form matches the known-branch
    # strength mapping, which for a real team differs from the debut default.
    assert rows[S.F_FORM_FINISH].iloc[0] != NO_HISTORY_FORM_FINISH


# ── root cause 2: unknown entry looks like a real debut, not a strong car ───

def test_unknown_entry_seeded_like_a_debut_row(results):
    sc = Scenario.from_results(results)
    rows = sc.features_from_grid([{"driver": "XYZ", "team": "Cadillac"}])
    r = rows.iloc[0]
    assert bool(r["no_history"]) is True
    assert r[S.F_FORM_FINISH] == NO_HISTORY_FORM_FINISH
    assert r[S.F_FORM_POINTS] == NO_HISTORY_FORM_POINTS
    assert r[S.F_CIRCUIT_HIST] == NO_HISTORY_CIRCUIT
    assert r[S.F_DRV_PTS_TD] == 0.0       # no fabricated season points
    assert r[S.F_TEAM_PTS_TD] == 0.0
    assert r[S.F_PRIOR_EXP] == 0.0


def test_debut_prior_matches_direct_parquet_style_query(results):
    """The debut prior must equal a direct 'first race per driver' query."""
    prior = derive_debut_prior(results)
    df = results.copy()
    df[S.DATE] = pd.to_datetime(df[S.DATE])
    firsts = df.sort_values([S.DATE, S.SEASON, S.ROUND]).drop_duplicates(
        subset=[S.DRIVER], keep="first")
    assert prior["expected_finish"] == round(float(firsts[S.FINISH].mean()), 3)
    assert prior["n_debuts"] == int(len(firsts))
    # Prior must be a back-of-midfield number, never the front.
    assert prior["expected_finish"] > 8.0


def test_unknown_does_not_rank_too_high_in_a_real_grid(feats, results, model):
    """A grid of KNOWN drivers plus one unknown: the unknown must land in the
    lower half, never ahead of the established front-runners (the original bug
    was an unknown finishing P4 of 7, ahead of clearly stronger drivers)."""
    sc = Scenario.from_results(results)
    known = list(sc.drivers.keys())
    known.sort(key=lambda d: -sc.drivers[d].pace_rating)  # strongest first
    grid = [{"driver": d, "team": sc.driver_team[d]} for d in known]
    # Insert an unknown, brand-new team midway down the grid.
    grid.insert(len(grid) // 2, {"driver": "XYZ", "team": "Cadillac"})

    order = model.predict_order(sc.features_from_grid(grid)).sort_values("predicted_position")
    n = len(order)
    xyz_pos = int(order.loc[order[S.DRIVER] == "XYZ", "predicted_position"].iloc[0])

    # Not ranked too high: must be in the bottom half of the field.
    assert xyz_pos > n / 2, f"Unknown ranked too high at P{xyz_pos} of {n}"
    # Concretely: it finishes behind the three strongest known drivers.
    top3 = set(order.nsmallest(3, "predicted_position")[S.DRIVER])
    assert "XYZ" not in top3
