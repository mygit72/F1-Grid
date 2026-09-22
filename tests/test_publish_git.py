"""Tests for the publish-and-commit-push routine (item 1).

Covered:
  * a published prediction is committed in a DEDICATED commit touching only that
    file, even when other changes are staged,
  * the commit message carries the prediction's content_hash (and it matches the
    file),
  * TRACK_RECORD.md regenerates byte-for-byte identically from the same inputs,
  * a simulated push failure is reported as a failure, never as success.

These use a throwaway git repo in a temp dir; no network and no real remote.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from f1grid import publish_git as PG
from f1grid import reporting as R


def _git(args, cwd):
    res = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True)
    assert res.returncode == 0, f"git {args} failed: {res.stderr or res.stdout}"
    return res.stdout.strip()


@pytest.fixture()
def repo(tmp_path):
    _git(["init", "-b", "main"], tmp_path)
    _git(["config", "user.email", "test@example.com"], tmp_path)
    _git(["config", "user.name", "Test"], tmp_path)
    (tmp_path / "README.md").write_text("seed\n", encoding="utf-8")
    _git(["add", "README.md"], tmp_path)
    _git(["commit", "-m", "seed"], tmp_path)
    return tmp_path


def _write_pred(dirpath: Path) -> Path:
    dirpath.mkdir(parents=True, exist_ok=True)
    rec = {
        "made_at_utc": "2026-09-21T11:35:07Z",
        "race_start_utc": "2026-09-26T11:00:00Z",
        "is_pre_race": True,
        "season": 2026,
        "round": 15,
        "event": "Azerbaijan Grand Prix",
        "prediction": [{"driver": "ANT", "predicted_position": 1}],
        "schema_version": 2,
        "content_hash": "74c95ccf0d",
        "nonce": "77fc5a",
    }
    p = dirpath / "2026_R15_Azerbaijan__x.json"
    p.write_text(json.dumps(rec, indent=2), encoding="utf-8")
    return p


def test_commit_contains_only_prediction_file(repo):
    pred = _write_pred(repo / "artifacts" / "predictions")
    # A DECOY unrelated change is also staged; it must NOT ride along.
    decoy = repo / "decoy.txt"
    decoy.write_text("do not commit me\n", encoding="utf-8")
    _git(["add", "decoy.txt"], repo)

    sha = PG.commit_only([pred], "msg", cwd=repo)
    files = _git(["show", "--name-only", "--pretty=format:", sha], repo).split()
    rel = str(pred.relative_to(repo)).replace("\\", "/")
    assert files == [rel], f"commit touched {files}, expected only {rel}"
    # decoy is still staged/uncommitted, proving it did not leak in.
    assert "decoy.txt" in _git(["status", "--porcelain"], repo)


def test_commit_message_carries_matching_hash(repo):
    pred = _write_pred(repo / "artifacts" / "predictions")
    rec = json.loads(pred.read_text(encoding="utf-8"))
    result = PG.publish_commit_push(
        pred, push=True,
        pusher=lambda *_: (True, "ok"),
        cwd=repo,
        track_record_path=repo / "TRACK_RECORD.md",
    )
    msg = _git(["log", "-1", "--format=%B", result["prediction_commit"]], repo)
    assert rec["content_hash"] in msg
    assert f"content_hash={rec['content_hash']}" in msg
    assert result["content_hash"] == rec["content_hash"]


def test_track_record_regenerates_identically(tmp_path):
    pred_dir = tmp_path / "preds"
    _write_pred(pred_dir)
    sc = tmp_path / "scorecard.csv"  # does not exist -> "no races scored" state
    first = R.render_track_record(scorecard=sc, pred_dir=pred_dir)
    second = R.render_track_record(scorecard=sc, pred_dir=pred_dir)
    assert first == second
    # And writing then re-rendering is stable too.
    out = tmp_path / "TR.md"
    R.write_track_record(out, scorecard=sc, pred_dir=pred_dir)
    assert out.read_text(encoding="utf-8") == first
    assert "Azerbaijan Grand Prix" in first  # the pending prediction is listed


def test_simulated_push_failure_reports_failure(repo):
    pred = _write_pred(repo / "artifacts" / "predictions")
    result = PG.publish_commit_push(
        pred, push=True,
        pusher=lambda *_: (False, "fatal: unable to access remote"),
        cwd=repo,
        track_record_path=repo / "TRACK_RECORD.md",
    )
    assert result["ok"] is False
    assert result["status"] == "push_failed_after_prediction_commit"
    assert result["pushes"][-1]["ok"] is False
    # The prediction was still committed locally (only the push failed).
    assert result["prediction_commit"] is not None


def test_successful_push_reports_ok(repo):
    pred = _write_pred(repo / "artifacts" / "predictions")
    pushes = []
    result = PG.publish_commit_push(
        pred, push=True,
        pusher=lambda r, b, c: (pushes.append((r, b)) or (True, "ok")),
        cwd=repo,
        track_record_path=repo / "TRACK_RECORD.md",
    )
    assert result["ok"] is True
    assert result["status"] == "pushed"
    # prediction push + track-record push both happened.
    assert len(pushes) == 2
    assert result["track_record_commit"] is not None
