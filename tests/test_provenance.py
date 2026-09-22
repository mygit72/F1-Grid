"""Tests for third-party provenance collection (item 1, verification correction).

No network: gh, curl, and the Wayback availability API are all monkeypatched.
The point is that the routine records real server timestamps when available and
records the exact error (never a fabricated value) when a step fails.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from f1grid import provenance as P


def _rec():
    return {
        "season": 2026, "round": 15, "event": "Azerbaijan Grand Prix",
        "content_hash": "74c95ccf0d",
        "made_at_utc": "2026-09-21T11:35:07Z",
        "race_start_utc": "2026-09-26T11:00:00Z",
    }


def test_release_tag_and_raw_url():
    assert P.release_tag(_rec()) == "pred-2026-R15"
    url = P.raw_file_url("owner/repo", Path("a/b/pred.json"), branch="main")
    assert url == "https://raw.githubusercontent.com/owner/repo/main/artifacts/predictions/pred.json"


def test_wayback_save_confirms_via_availability(monkeypatch):
    monkeypatch.setattr(P, "_curl_trigger", lambda url, timeout: None)
    snap = ("http://web.archive.org/web/20260922105143/"
            "https://raw.githubusercontent.com/owner/repo/main/artifacts/predictions/pred.json")
    monkeypatch.setattr(P, "_curl_json", lambda url, timeout: {
        "archived_snapshots": {"closest": {
            "available": True, "status": "200",
            "url": snap, "timestamp": "20260922105143"}}})
    out = P.wayback_save("https://raw.githubusercontent.com/owner/repo/main/artifacts/predictions/pred.json")
    assert out["snapshot_url"] == snap
    assert out["timestamp"] == "2026-09-22T10:51:43Z"
    assert out["raw_timestamp"] == "20260922105143"


def test_wayback_save_raises_exact_error_when_no_snapshot(monkeypatch):
    monkeypatch.setattr(P, "_curl_trigger", lambda url, timeout: None)
    monkeypatch.setattr(P, "_curl_json", lambda url, timeout: {"archived_snapshots": {}})
    with pytest.raises(RuntimeError, match="no confirmed snapshot"):
        P.wayback_save("https://example.com/x.json")


def test_sidecar_roundtrip(tmp_path):
    pred = tmp_path / "pred.json"
    pred.write_text("{}", encoding="utf-8")
    data = {"content_hash": "abc", "release": {"published_at": "2026-09-22T10:50:56Z"}}
    P.write_provenance(pred, data, prov_dir=tmp_path / "prov")
    back = P.read_provenance(pred, prov_dir=tmp_path / "prov")
    assert back == data
    assert P.read_provenance(tmp_path / "missing.json", prov_dir=tmp_path / "prov") is None


def test_collect_provenance_records_errors_not_fakes(monkeypatch, tmp_path):
    """If a proof step fails, the sidecar records the error string, and no other
    step is faked. Nothing invents a timestamp."""
    def boom(*a, **k):
        raise RuntimeError("release boom")
    monkeypatch.setattr(P, "create_github_release", boom)
    monkeypatch.setattr(P, "push_event_created_at", lambda repo, gh=None: "2026-09-22T10:00:00Z")
    monkeypatch.setattr(P, "wayback_save", lambda url, timeout=150: {
        "snapshot_url": "http://web.archive.org/web/20260922105143/x",
        "timestamp": "2026-09-22T10:51:43Z", "raw_timestamp": "20260922105143"})

    pred = tmp_path / "pred.json"
    pred.write_text("{}", encoding="utf-8")
    data = P.collect_provenance("owner/repo", pred, _rec(), "deadbeef",
                                prov_dir=tmp_path / "prov")
    assert data["release_error"] == "release boom"
    assert "release" not in data  # not faked
    assert data["push_event_created_at"] == "2026-09-22T10:00:00Z"
    assert data["wayback"]["timestamp"] == "2026-09-22T10:51:43Z"
    # sidecar was written
    assert P.read_provenance(pred, prov_dir=tmp_path / "prov")["release_error"] == "release boom"


def test_publish_commit_push_commits_sidecar(tmp_path, monkeypatch):
    """With a repo set, the routine collects provenance and commits the sidecar
    alongside the track record."""
    import subprocess
    from f1grid import publish_git as PG

    def g(args):
        r = subprocess.run(["git", *args], cwd=str(tmp_path), capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        return r.stdout.strip()

    g(["init", "-b", "main"]); g(["config", "user.email", "t@e.com"]); g(["config", "user.name", "t"])
    (tmp_path / "seed").write_text("x", encoding="utf-8"); g(["add", "seed"]); g(["commit", "-m", "seed"])

    pred_dir = tmp_path / "artifacts" / "predictions"
    pred_dir.mkdir(parents=True)
    pred = pred_dir / "2026_R15_pred.json"
    pred.write_text(json.dumps({**_rec()}, indent=2), encoding="utf-8")

    prov_dir = tmp_path / "artifacts" / "provenance"

    def fake_collect(repo, pred_path, rec, sha, **k):
        d = {"prediction_file": Path(pred_path).name, "content_hash": rec["content_hash"],
             "commit_sha": sha, "race_start_utc": rec["race_start_utc"],
             "release": {"url": "u", "published_at": "2026-09-22T10:50:56Z"}}
        P.write_provenance(pred_path, d, prov_dir=k.get("prov_dir", prov_dir))
        return d
    monkeypatch.setattr(PG.prov, "collect_provenance", fake_collect)

    result = PG.publish_commit_push(
        pred, repo="owner/repo", push=True, pusher=lambda *_: (True, "ok"),
        cwd=tmp_path, track_record_path=tmp_path / "TRACK_RECORD.md",
        prov_dir=prov_dir, do_wayback=False,
        # keep TRACK_RECORD generation reading the temp dirs, not the real repo
    )
    assert result["ok"] is True
    assert result["provenance"]["release"]["published_at"] == "2026-09-22T10:50:56Z"
    # the sidecar is part of the track-record commit
    files = g(["show", "--name-only", "--pretty=format:", result["track_record_commit"]])
    assert "provenance" in files
