"""Deployed-mode safety for publishing (item 3).

In deployment mode (env var F1GRID_DEPLOYED truthy) the write endpoints (publish,
score) are refused with HTTP 403, while every read-only endpoint keeps working.
In local mode nothing changes: publish is NOT refused for the deployment reason
(it may still hit the pre-race boundary, but that is a different, 409, path).
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from f1grid import schema as S
from f1grid import runtime
from f1grid.features.build import build_features
from f1grid.model.pipeline import TwoStagePipeline
from f1grid.model.panel import Scenario
from tests.synthetic import make_synthetic

from api import main as api_main


class _FakeState:
    def __init__(self):
        results = make_synthetic(seasons=(2023, 2024, 2025), rounds_per_season=8, seed=7)
        self.results = results
        self.feats = build_features(results)
        self.pipeline = TwoStagePipeline().fit(
            self.feats[self.feats["race_id"] < self.feats["race_id"].max()])
        self.is_real_data = True
        self.used_saved_models = True
        self.scenario = Scenario.from_results(results)
        self.laps = None

    def strategy_meter(self, season, round_no, event):
        return {"label": "Strategy complexity", "is_confidence": False,
                "state": "no_history", "level": None, "score": None,
                "reason": "synthetic", "signals": {}, "components_used": []}


@pytest.fixture()
def fake_state(monkeypatch):
    st = _FakeState()
    monkeypatch.setattr(api_main, "get_state", lambda: st)
    return st


def _a_race(st):
    season = int(st.feats[S.SEASON].max())
    rnd = int(st.feats[st.feats[S.SEASON] == season][S.ROUND].max())
    return season, rnd


def test_deployed_refuses_publish_and_score(fake_state, monkeypatch):
    monkeypatch.setenv(runtime.DEPLOYED_ENV_VAR, "1")
    assert runtime.is_deployed() is True
    season, rnd = _a_race(fake_state)

    with pytest.raises(HTTPException) as ei:
        api_main.publish_prediction(season, rnd, rain_prob=0.0,
                                    use_real_grid=False, backtest=False)
    assert ei.value.status_code == 403
    # Even the backtest route is refused in deployed mode.
    with pytest.raises(HTTPException) as ei2:
        api_main.publish_prediction(season, rnd, rain_prob=0.0,
                                    use_real_grid=False, backtest=True)
    assert ei2.value.status_code == 403

    with pytest.raises(HTTPException) as ei3:
        api_main.score_prediction(season, rnd)
    assert ei3.value.status_code == 403


def test_deployed_read_only_still_works(fake_state, monkeypatch):
    monkeypatch.setenv(runtime.DEPLOYED_ENV_VAR, "1")
    season, rnd = _a_race(fake_state)

    # predictions (with the meter), track record, scenario defaults, manual grid.
    resp = api_main.get_prediction(season, rnd, rain_prob=0.0, use_real_grid=False)
    assert resp.predictions and resp.strategy_meter is not None
    assert api_main.list_races(season=None) != []
    assert "teams" in api_main.scenario_defaults()
    mg = api_main.predict_manual_grid([{"driver": "D00", "team": "RBR"},
                                       {"driver": "D01", "team": "FER"}])
    assert mg["predicted_finish"]
    # track-record endpoint returns (possibly empty) without error
    api_main.track_record()


def test_local_mode_does_not_refuse_for_deployment(fake_state, monkeypatch):
    monkeypatch.delenv(runtime.DEPLOYED_ENV_VAR, raising=False)
    assert runtime.is_deployed() is False
    season, rnd = _a_race(fake_state)
    # In local mode the deployment guard is absent. Publishing a synthetic race
    # with no authoritative schedule raises the retroactive/boundary error (or
    # succeeds), but NEVER the 403 deployment refusal.
    try:
        api_main.publish_prediction(season, rnd, rain_prob=0.0,
                                    use_real_grid=False, backtest=True)
    except HTTPException as e:
        assert e.status_code != 403


def test_is_deployed_parsing(monkeypatch):
    for val, expected in [("1", True), ("true", True), ("YES", True), ("on", True),
                          ("0", False), ("false", False), ("", False), ("nope", False)]:
        monkeypatch.setenv(runtime.DEPLOYED_ENV_VAR, val)
        assert runtime.is_deployed() is expected
    monkeypatch.delenv(runtime.DEPLOYED_ENV_VAR, raising=False)
    assert runtime.is_deployed() is False
