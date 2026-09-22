"""Item 3: medal release notes + README track record.

Covered:
  * prediction notes render from the file only (fields present in the file), and
    show a strategy meter only when the file has one,
  * the prediction section is byte-for-byte unchanged after a result is appended,
  * no result section appears until one is appended,
  * medals and markers are correct for exact, shifted, and missed podium picks,
  * content_hash verification catches a tampered file,
  * the README track record regenerates identically and shows "pending" for an
    ungraded race.
"""
from __future__ import annotations

import hashlib
import json

import pandas as pd

from f1grid import release_notes as RN
from f1grid import reporting as R


def _make_rec(drivers_teams, *, season=2026, round_no=15, event="Test GP",
              meter=None):
    """Build a store-shaped record whose content_hash verifies."""
    order = []
    for i, (drv, team) in enumerate(drivers_teams, start=1):
        order.append({
            "driver": drv, "team": team, "predicted_position": i,
            "win_prob": round(0.4 / i, 6), "podium_prob": round(0.7 / i, 6),
            "points_prob": round(0.9 / i, 6),
        })
    rec = {
        "made_at_utc": "2026-09-21T11:35:07Z",
        "race_start_utc": "2026-09-26T11:00:00Z",
        "is_pre_race": True, "is_backtest": False, "data_cutoff": "as of 2026 R14",
        "season": season, "round": round_no, "event": event, "rain_prob": 0.0,
        "model_meta": {}, "prediction": order, "schema_version": 3,
    }
    if meter is not None:
        rec["strategy_meter"] = meter
    payload = json.dumps(rec, sort_keys=True, default=str)
    rec["content_hash"] = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:10]
    rec["nonce"] = "abc123"
    return rec


DT = [("ANT", "Mercedes"), ("RUS", "Mercedes"), ("NOR", "McLaren"),
      ("PIA", "McLaren"), ("HAM", "Ferrari")]


def test_notes_render_from_file_only_and_verify():
    rec = _make_rec(DT)
    assert RN.verify_content_hash(rec)
    notes = RN.render_prediction_notes(rec, "file.json")
    # podium drivers with medals present
    assert "\U0001F947 P1 - ANT" in notes
    assert "\U0001F948 P2 - RUS" in notes
    assert "\U0001F949 P3 - NOR" in notes
    # verification details + source-of-truth line
    assert f"content_hash: `{rec['content_hash']}`" in notes
    assert "source of truth" in notes
    assert "never edited after the race" in notes


def test_tampered_file_fails_verification():
    rec = _make_rec(DT)
    rec["prediction"][0]["win_prob"] = 0.99999  # tamper after hashing
    assert not RN.verify_content_hash(rec)


def test_meter_shown_only_when_present():
    without = RN.render_prediction_notes(_make_rec(DT), "f.json")
    assert "Strategy complexity" not in without
    with_meter = RN.render_prediction_notes(
        _make_rec(DT, meter={"label": "Strategy complexity", "level": "Med",
                             "state": "ok", "reason": "moderate pit spread"}),
        "f.json")
    assert "Strategy complexity" in with_meter
    assert "moderate pit spread" in with_meter


def test_absent_probability_column_is_omitted():
    rec = _make_rec(DT)
    for row in rec["prediction"]:
        del row["points_prob"]
    notes = RN.render_prediction_notes(rec, "f.json")
    assert "Points" not in notes
    assert "Win" in notes and "Podium" in notes


def test_no_result_block_until_appended():
    body = RN.compose_body(_make_rec(DT), "f.json")
    assert RN.PRED_BEGIN in body and RN.PRED_END in body
    assert RN.RESULT_BEGIN not in body


def test_prediction_block_unchanged_after_result_appended():
    rec = _make_rec(DT)
    body = RN.compose_body(rec, "f.json")
    grade = {"spearman": 0.5, "top1_acc": 1.0, "podium_acc": 0.6667,
             "mae_pos": 2.0, "beat_baseline": 1.0, "baseline_used": "grid_order",
             "baseline_spearman": 0.4}
    actual = [{"driver": "ANT", "finish": 1, "team": "Mercedes"},
              {"driver": "NOR", "finish": 2, "team": "McLaren"},
              {"driver": "VER", "finish": 3, "team": "Red Bull"}]
    result = RN.render_result_section(rec, grade, actual)
    new = RN.append_result_block(body, result)
    assert RN.extract_prediction_block(body) == RN.extract_prediction_block(new)
    assert RN.RESULT_BEGIN in new


def test_medals_and_markers_exact_shifted_missed():
    rec = _make_rec(DT)  # predicted podium ANT, RUS, NOR
    # actual: ANT P1 (exact), NOR P2 (predicted P3 -> shifted), VER P3;
    # RUS predicted P2 but finished off the podium (missed).
    actual = [{"driver": "ANT", "finish": 1, "team": "Mercedes"},
              {"driver": "NOR", "finish": 2, "team": "McLaren"},
              {"driver": "VER", "finish": 3, "team": "Red Bull"},
              {"driver": "RUS", "finish": 4, "team": "Mercedes"}]
    grade = {"spearman": 0.6, "top1_acc": 1.0, "podium_acc": 0.6667,
             "mae_pos": 1.5, "beat_baseline": 0.0, "baseline_used": "grid_order",
             "baseline_spearman": 0.7}
    res = RN.render_result_section(rec, grade, actual)
    lines = res.splitlines()
    p1 = next(l for l in lines if "P1 |" in l)
    p2 = next(l for l in lines if "P2 |" in l)
    p3 = next(l for l in lines if "P3 |" in l)
    assert RN.EXACT in p1              # ANT exact
    assert RN.MISSED in p2             # RUS missed the podium
    assert RN.SHIFTED in p3            # NOR on podium, wrong slot
    assert "Podium hits: 2/3" in res
    assert "Beat baseline: NO" in res


def _write_rec(pred_dir, rec):
    name = f"{rec['season']}_R{rec['round']:02d}_Test__x__{rec['content_hash']}_n.json"
    (pred_dir / name).write_text(json.dumps(rec, indent=2), encoding="utf-8")


def test_readme_track_record_regenerates_identically_and_pending(tmp_path):
    pred_dir = tmp_path / "pred"
    prov_dir = tmp_path / "prov"
    pred_dir.mkdir()
    prov_dir.mkdir()
    _write_rec(pred_dir, _make_rec(DT))
    scorecard = tmp_path / "scorecard.csv"  # does not exist -> nothing graded

    a = R.render_readme_track_record(scorecard, pred_dir, prov_dir)
    b = R.render_readme_track_record(scorecard, pred_dir, prov_dir)
    assert a == b                          # deterministic
    assert "pending" in a                  # ungraded race shows pending
    assert "0 race(s) graded" in a


def test_readme_update_is_idempotent(tmp_path):
    pred_dir = tmp_path / "pred"
    prov_dir = tmp_path / "prov"
    pred_dir.mkdir()
    prov_dir.mkdir()
    _write_rec(pred_dir, _make_rec(DT))
    scorecard = tmp_path / "sc.csv"
    readme = tmp_path / "README.md"
    readme.write_text("# Title\n\n## Architecture\n\nstuff\n", encoding="utf-8")

    R.update_readme_track_record(readme, scorecard, pred_dir, prov_dir)
    first = readme.read_text(encoding="utf-8")
    R.update_readme_track_record(readme, scorecard, pred_dir, prov_dir)
    second = readme.read_text(encoding="utf-8")
    assert first == second
    assert first.count(R.README_TR_BEGIN) == 1
    assert "## Architecture" in first
