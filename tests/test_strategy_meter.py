"""Tests for the circuit strategy-disruption meter (item 2).

Covered:
  * leakage: the meter for a race is unchanged when that race's OWN result is
    corrupted (it uses only prior races),
  * the no-history state for a circuit with no prior races,
  * buckets/score are computed ONLY from prior races (future races do not move
    them; changing a prior race does),
  * old prediction files (no strategy_meter field) still load and hash-verify,
    and a new record carrying the field also verifies,
  * the UI label switches correctly with the validated label_mode.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from f1grid import schema as S
from f1grid.model import strategy_meter as SM
from f1grid.store.predictions import load_predictions


def _results():
    """Two circuits across three seasons; deterministic grid/finish."""
    rows = []
    for season in (2022, 2023, 2024):
        for rnd, ev in [(1, "Alpha GP"), (2, "Beta GP")]:
            for i in range(10):
                grid = i + 1
                # Alpha: finish == grid (processional). Beta: reversed (shuffle).
                finish = grid if ev == "Alpha GP" else (10 - i)
                rows.append({S.SEASON: season, S.ROUND: rnd, S.EVENT: ev,
                             S.DRIVER: f"D{i:02d}", S.TEAM: f"T{i//2}",
                             S.GRID: grid, S.FINISH: finish, S.DNF: 0})
    return pd.DataFrame(rows)


def _laps():
    """Minimal laps: Beta races have a safety car and varied pit counts; Alpha
    has none. One row per driver is enough for the aggregates used."""
    rows = []
    for season in (2022, 2023, 2024):
        for rnd, ev in [(1, "Alpha GP"), (2, "Beta GP")]:
            for i in range(10):
                pits = (i % 3) if ev == "Beta GP" else 1  # varied vs uniform
                status = "14" if ev == "Beta GP" else "1"
                rows.append({S.SEASON: season, S.ROUND: rnd, S.EVENT: ev,
                             S.DRIVER: f"D{i:02d}", "is_pit_in": pits,
                             "track_status": status})
    return pd.DataFrame(rows)


def test_no_history_state():
    res, laps = _results(), _laps()
    # A circuit never seen before -> no history, no guessed value.
    m = SM.classify(res, laps, "Brand New GP", 2024, 3, thresholds={"t1": 0.3, "t2": 0.6})
    assert m["state"] == "no_history"
    assert m["level"] is None and m["score"] is None


def test_leakage_meter_unchanged_by_own_result():
    res, laps = _results(), _laps()
    # Beta GP 2024 R2 uses prior Beta races (2022, 2023); its own result must
    # not affect the score.
    SM.assert_no_leakage(res, laps, "Beta GP", 2024, 2)
    SM.assert_no_leakage(res, laps, "Alpha GP", 2024, 1)


def test_buckets_use_only_prior_races():
    res, laps = _results(), _laps()
    ev, season, rnd = "Beta GP", 2024, 2
    base = SM.meter_score(res, laps, ev, season, rnd)
    # Removing the current race must not change the score (only prior races count).
    trimmed = res[~((res[S.SEASON] == season) & (res[S.ROUND] == rnd))]
    same = SM.meter_score(trimmed, laps, ev, season, rnd)
    assert base["score"] == same["score"]
    # Changing a PRIOR race (make 2022 Beta processional) DOES change it.
    altered = res.copy()
    m2022 = (altered[S.SEASON] == 2022) & (altered[S.EVENT] == "Beta GP")
    altered.loc[m2022, S.FINISH] = altered.loc[m2022, S.GRID].values
    changed = SM.meter_score(altered, laps, ev, season, rnd)
    assert changed["score"] != base["score"]


def test_beta_more_disruptive_than_alpha():
    res, laps = _results(), _laps()
    beta = SM.meter_score(res, laps, "Beta GP", 2024, 2)["score"]
    alpha = SM.meter_score(res, laps, "Alpha GP", 2024, 1)["score"]
    assert beta > alpha  # reversed-order circuit scores higher disruption


def test_label_switches_with_validated_mode(tmp_path):
    res, laps = _results(), _laps()
    art = tmp_path / "meter.json"
    common = {"t1": 0.3, "t2": 0.6}
    art.write_text(json.dumps({**common, "label_mode": "complexity"}), encoding="utf-8")
    m = SM.classify_from_artifact(res, laps, "Beta GP", 2024, 2, artifact=art)
    assert m["label"] == "Strategy complexity" and m["is_confidence"] is False

    art.write_text(json.dumps({**common, "label_mode": "confidence"}), encoding="utf-8")
    m2 = SM.classify_from_artifact(res, laps, "Beta GP", 2024, 2, artifact=art)
    assert m2["label"] == "Prediction confidence (strategy-based)"
    assert m2["is_confidence"] is True


def _recompute_hash(rec: dict) -> str:
    payload_rec = {k: v for k, v in rec.items()
                   if k not in ("content_hash", "nonce", "_path")}
    payload = json.dumps(payload_rec, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:10]


def test_old_and_new_prediction_files_both_verify(tmp_path):
    pred_dir = tmp_path / "preds"
    pred_dir.mkdir()
    # OLD-style record: no strategy_meter field (schema v2).
    old = {"made_at_utc": "2026-09-21T11:35:07Z", "season": 2026, "round": 15,
           "event": "Azerbaijan Grand Prix", "prediction": [{"driver": "ANT"}],
           "schema_version": 2}
    old["content_hash"] = _recompute_hash(old)
    (pred_dir / "old.json").write_text(json.dumps(old, indent=2), encoding="utf-8")
    # NEW-style record: WITH strategy_meter field (schema v3).
    new = {"made_at_utc": "2026-10-01T10:00:00Z", "season": 2026, "round": 16,
           "event": "Singapore Grand Prix", "prediction": [{"driver": "VER"}],
           "schema_version": 3,
           "strategy_meter": {"label": "Strategy complexity", "is_confidence": False,
                              "state": "ok", "level": "Medium", "score": 0.71,
                              "reason": "x", "components_used": ["divergence_norm"]}}
    new["content_hash"] = _recompute_hash(new)
    (pred_dir / "new.json").write_text(json.dumps(new, indent=2), encoding="utf-8")

    recs = load_predictions(pred_dir=pred_dir)
    assert len(recs) == 2
    for rec in recs:
        assert _recompute_hash(rec) == rec["content_hash"]
    by_round = {r["round"]: r for r in recs}
    assert "strategy_meter" not in by_round[15]      # old still valid
    assert by_round[16]["strategy_meter"]["level"] == "Medium"  # new carries it
