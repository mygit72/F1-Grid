"""Retroactive-prediction boundary tests (item 6) - tested most heavily.

The public track record's whole value is that every prediction in it was
committed BEFORE the race. These tests attack that boundary from every angle:
future ok, finished refused, within-minutes, timezone edges, and adversarial
attempts (forged future start, publish via the API, backtest leakage).

Two invariants underpin all of it:
  * `made_at` is the store's own clock, never caller-supplied  -> no backdating.
  * the race start is looked up authoritatively and overrides any caller value
    -> no faking a future start for a race that already ran.
"""
from __future__ import annotations

import json
import shutil
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd
import pytest

from f1grid import schema as S
from f1grid.features.build import build_features
from f1grid.model.pipeline import TwoStagePipeline
from f1grid.store import predictions as PS
from f1grid.store.predictions import save_prediction, RetroactivePredictionError
from f1grid.score import scorer as SC
from tests.synthetic import make_synthetic

UTC = timezone.utc


@pytest.fixture()
def stores():
    tmp = Path(tempfile.mkdtemp())
    pub, bt = tmp / "pub", tmp / "bt"
    pub.mkdir(); bt.mkdir()
    yield pub, bt
    shutil.rmtree(tmp)


def _pred_df():
    return pd.DataFrame({
        S.DRIVER: ["A", "B", "C", "D", "E"],
        S.TEAM: ["T1", "T1", "T2", "T2", "T3"],
        "predicted_position": [1, 2, 3, 4, 5],
    })


def _save(pub, *, start, now, race=(2030, 1), backtest=False, bt=None,
          forged_start=None):
    """Helper: save with an injected authoritative start and clock."""
    return save_prediction(
        race[0], race[1], "Test GP", _pred_df(), data_cutoff="cut",
        pred_dir=pub, backtest_dir=(bt or pub.parent / "bt"), backtest=backtest,
        race_start_utc=forged_start, schedule_lookup=lambda *_: start, now_utc=now,
    )


# ── 1. a future race publishes successfully ─────────────────────────────────

def test_future_race_publishes_to_public(stores):
    pub, bt = stores
    start = datetime(2030, 6, 1, 12, tzinfo=UTC)
    path = _save(pub, start=start, now=start - timedelta(hours=2), bt=bt)
    assert path.exists() and path.parent == pub
    rec = json.loads(path.read_text(encoding="utf-8"))
    assert rec["is_pre_race"] is True and rec["is_backtest"] is False
    assert rec["race_start_utc"] == "2030-06-01T12:00:00Z"


# ── 2. a finished race is refused from the public record ────────────────────

def test_finished_race_is_refused(stores):
    pub, bt = stores
    start = datetime(2020, 6, 1, 12, tzinfo=UTC)
    with pytest.raises(RetroactivePredictionError):
        _save(pub, start=start, now=datetime(2026, 9, 21, tzinfo=UTC), bt=bt)
    assert list(pub.glob("*.json")) == []  # nothing leaked into the public store


# ── 3. a race starting within minutes ───────────────────────────────────────

def test_within_minutes_of_start(stores):
    pub, bt = stores
    start = datetime(2030, 6, 1, 12, 0, 0, tzinfo=UTC)
    # 1 minute BEFORE -> allowed
    ok = _save(pub, start=start, now=start - timedelta(minutes=1), bt=bt)
    assert ok.exists()
    # exactly AT start -> refused (must be strictly before)
    with pytest.raises(RetroactivePredictionError):
        _save(pub, start=start, now=start, bt=bt)
    # 1 minute AFTER -> refused
    with pytest.raises(RetroactivePredictionError):
        _save(pub, start=start, now=start + timedelta(minutes=1), bt=bt)


# ── 4. timezone edge cases around start ─────────────────────────────────────

def test_timezone_edges(stores):
    pub, bt = stores
    # Start expressed in +09:00 -> 03:00 UTC. Compare against a UTC clock.
    start_local = datetime(2030, 6, 1, 12, tzinfo=timezone(timedelta(hours=9)))
    # 02:59 UTC (before) -> ok
    ok = _save(pub, start=start_local, now=datetime(2030, 6, 1, 2, 59, tzinfo=UTC), bt=bt)
    assert ok.exists()
    # 03:01 UTC (after) -> refused
    with pytest.raises(RetroactivePredictionError):
        _save(pub, start=start_local, now=datetime(2030, 6, 1, 3, 1, tzinfo=UTC), bt=bt)
    # A NAIVE authoritative start must be treated as UTC, not local machine time.
    naive = datetime(2030, 6, 1, 12)  # no tzinfo
    ok2 = _save(pub, start=naive, now=datetime(2030, 6, 1, 11, 59, tzinfo=UTC),
                race=(2030, 2), bt=bt)
    assert ok2.exists()
    with pytest.raises(RetroactivePredictionError):
        _save(pub, start=naive, now=datetime(2030, 6, 1, 12, 1, tzinfo=UTC),
              race=(2030, 3), bt=bt)


# ── 5a. adversarial: forged future start cannot override authority ──────────

def test_forged_future_start_cannot_beat_authoritative_past(stores):
    pub, bt = stores
    real_past = datetime(2025, 4, 20, 17, tzinfo=UTC)   # authoritative: already ran
    forged_future = datetime(2099, 1, 1, tzinfo=UTC)     # caller lies
    with pytest.raises(RetroactivePredictionError):
        _save(pub, start=real_past, now=datetime(2026, 9, 21, tzinfo=UTC),
              race=(2025, 5), forged_start=forged_future, bt=bt)
    assert list(pub.glob("*.json")) == []


# ── 5b. adversarial: backtest of a finished race is quarantined ─────────────

def test_backtest_of_finished_race_is_separate_and_never_public(stores):
    pub, bt = stores
    real_past = datetime(2025, 4, 20, 17, tzinfo=UTC)
    path = _save(pub, start=real_past, now=datetime(2026, 9, 21, tzinfo=UTC),
                 race=(2025, 5), backtest=True, bt=bt)
    assert path.parent == bt and path.name.startswith("BACKTEST_")
    rec = json.loads(path.read_text(encoding="utf-8"))
    assert rec["is_backtest"] is True and rec["is_pre_race"] is False
    # The PUBLIC loader and scorer never see it.
    assert list(pub.glob("*.json")) == []
    assert PS.load_predictions(2025, 5, pred_dir=pub) == []
    assert SC.score_race(2025, 5, make_synthetic(), scorecard=bt / "sc.csv",
                         pred_dir=pub) is None


# ── 5c. adversarial: the same hole via the API is closed ────────────────────

class _FakeState:
    def __init__(self, feats, pipe):
        self.feats = feats
        self.pipeline = pipe
        self.used_saved_models = False
        self.is_real_data = False


def test_api_publish_refuses_finished_race(monkeypatch):
    from api import main as api_main
    from fastapi import HTTPException

    results = make_synthetic(seasons=(2023, 2024, 2025), rounds_per_season=8, seed=3)
    feats = build_features(results)
    pipe = TwoStagePipeline().fit(feats[feats["race_id"] < feats["race_id"].max()])
    monkeypatch.setattr(api_main, "get_state", lambda: _FakeState(feats, pipe))
    # Authoritative schedule says this race already started (the API has no way to
    # pass a timestamp, so made_at is the real clock - both doors are shut).
    monkeypatch.setattr(PS._schedule, "race_start_utc",
                        lambda s, r: datetime(2020, 1, 1, tzinfo=UTC))

    season = int(feats[S.SEASON].max())
    rnd = int(feats[feats[S.SEASON] == season][S.ROUND].max())
    # Called directly (not via FastAPI), so pass the Query params explicitly.
    with pytest.raises(HTTPException) as ei:
        api_main.publish_prediction(season, rnd, rain_prob=0.0,
                                    use_real_grid=False, backtest=False)
    assert ei.value.status_code == 409

    # But the explicit backtest route is allowed and stays out of the public store.
    resp = api_main.publish_prediction(season, rnd, rain_prob=0.0,
                                       use_real_grid=False, backtest=True)
    assert resp["published"] is True and resp["backtest"] is True
    assert "BACKTEST_" in Path(resp["file"]).name
    Path(resp["file"]).unlink()  # clean up the archive file this test created


# ── CLI: publish_next writes a genuine PUBLIC pre-race prediction ────────────

def test_publish_next_cli_publishes_future_race(monkeypatch):
    from f1grid import publish as pub

    results = make_synthetic(seasons=(2024, 2025), rounds_per_season=8, seed=5)
    upcoming = {"season": 2026, "round": 1, "event": "Opening GP",
                "race_start_utc": datetime(2030, 3, 1, 12, tzinfo=UTC)}
    now = datetime(2030, 2, 20, tzinfo=UTC)  # before the race
    monkeypatch.setattr(pub, "load_results", lambda: results)
    monkeypatch.setattr(pub.sched, "next_upcoming_race", lambda season, now_utc=None: upcoming)
    monkeypatch.setattr(PS._schedule, "race_start_utc",
                        lambda s, r: upcoming["race_start_utc"])

    path = pub.publish_next(season=2026, now_utc=now)
    assert path is not None and path.exists()
    try:
        rec = json.loads(path.read_text(encoding="utf-8"))
        assert rec["is_pre_race"] is True and rec["is_backtest"] is False
        assert rec["season"] == 2026 and rec["round"] == 1
        assert len(rec["prediction"]) > 10  # a full field was predicted
    finally:
        path.unlink()  # keep the real public store clean
