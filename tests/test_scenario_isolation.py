"""Scenario isolation regression tests (item 2).

Root cause guarded against: the API's POST /scenario/predict used to call
`sc.set_team`/`sc.set_driver` directly on the SHARED, cached `state.scenario`.
One caller's override therefore persisted across requests, so a later
GET /scenario/defaults returned the mutated value instead of the real
data-derived default. The fix applies every override to a per-request copy
(`state.scenario.copy()`), leaving the shared defaults untouched.
"""
from __future__ import annotations

import copy

import pytest

from f1grid import schema as S
from f1grid.features.build import build_features
from f1grid.model.panel import Scenario
from f1grid.model.pipeline import TwoStagePipeline
from tests.synthetic import make_synthetic

from api import main as api_main
from api.schemas import ScenarioOverride


@pytest.fixture(scope="module")
def results():
    return make_synthetic(seasons=(2023, 2024, 2025), rounds_per_season=10, seed=7)


@pytest.fixture(scope="module")
def feats(results):
    return build_features(results)


class _FakeState:
    """Minimal stand-in for api.state.AppState for the two scenario endpoints."""
    def __init__(self, scenario, feats, pipeline):
        self.scenario = scenario
        self.feats = feats
        self.pipeline = pipeline
        self.is_real_data = False


@pytest.fixture(scope="module")
def fake_state(results, feats):
    sc = Scenario.from_results(results)
    train = feats[feats["race_id"] < feats["race_id"].max()]
    pipe = TwoStagePipeline().fit(train)
    return _FakeState(sc, feats, pipe)


# ── unit-level: copy() truly isolates ───────────────────────────────────────

def test_copy_is_independent(results):
    sc = Scenario.from_results(results)
    team = next(iter(sc.teams))
    original = sc.teams[team].car_pace

    clone = sc.copy()
    clone.set_team(team, car_pace=original + 0.123 if original < 0.8 else 0.111)

    assert sc.teams[team].car_pace == original, "Mutating the copy changed the original"
    assert clone.teams[team].car_pace != original


# ── API endpoint level: shared defaults never mutated ───────────────────────

def _last_race(feats):
    rid = feats["race_id"].max()
    row = feats[feats["race_id"] == rid].iloc[0]
    return int(row[S.SEASON]), int(row[S.ROUND])


def test_override_does_not_change_defaults(monkeypatch, fake_state, feats):
    monkeypatch.setattr(api_main, "get_state", lambda: fake_state)
    season, rnd = _last_race(feats)

    defaults_before = copy.deepcopy(api_main.scenario_defaults())
    real_wil_pace = defaults_before["teams"]["WIL"]["car_pace"]
    assert real_wil_pace != 1.0  # sanity: the real default is not the override value

    ov = ScenarioOverride(team="WIL", team_dials={"car_pace": 1.0})
    api_main.scenario_predict(season, rnd, ov)

    defaults_after = api_main.scenario_defaults()
    assert defaults_after["teams"]["WIL"]["car_pace"] == real_wil_pace
    assert defaults_after == defaults_before, "GET /scenario/defaults changed after an override"


def test_two_overrides_are_independent(monkeypatch, fake_state, feats):
    monkeypatch.setattr(api_main, "get_state", lambda: fake_state)
    season, rnd = _last_race(feats)

    res_hi = api_main.scenario_predict(
        season, rnd, ScenarioOverride(team="WIL", team_dials={"car_pace": 1.0}))
    res_lo = api_main.scenario_predict(
        season, rnd, ScenarioOverride(team="WIL", team_dials={"car_pace": 0.0}))

    def wil_positions(res):
        return [r["predicted_position"] for r in res if r["team"] == "WIL"]

    hi = sum(wil_positions(res_hi))
    lo = sum(wil_positions(res_lo))
    # A maxed-out car should finish ahead of a zeroed-out one -> smaller position sum.
    assert hi < lo, ("Back-to-back overrides leaked into each other: a car_pace=1.0 "
                     "run did not beat a car_pace=0.0 run")


def test_defaults_identical_before_and_after_a_run_of_overrides(monkeypatch, fake_state, feats):
    monkeypatch.setattr(api_main, "get_state", lambda: fake_state)
    season, rnd = _last_race(feats)

    before = copy.deepcopy(api_main.scenario_defaults())
    for pace in (0.0, 0.25, 0.5, 0.75, 1.0):
        api_main.scenario_predict(
            season, rnd, ScenarioOverride(team="WIL", team_dials={"car_pace": pace}))
        api_main.scenario_predict(
            season, rnd, ScenarioOverride(driver="D12", driver_dials={"pace_rating": pace}))
    after = api_main.scenario_defaults()

    assert after == before, "Defaults drifted after a run of overrides"
