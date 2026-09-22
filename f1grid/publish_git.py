"""Publish-and-commit routine: turn a published prediction file into git history.

The flow, matching the process contract:
  1. commit ONLY the new prediction file (a dedicated single-file commit whose
     message carries the race, made_at, and content_hash),
  2. push,
  3. regenerate TRACK_RECORD.md and commit it,
  4. push.

A failed push is reported as a failure and never as a success. The push is a
single injectable callable so the failure path is testable without a network.

Nothing here regenerates or edits a prediction file: it only stages, commits,
and pushes what already exists. Already-published files are immutable.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Callable

from f1grid.config import ROOT
from f1grid.reporting import write_track_record, TRACK_RECORD_PATH

# A pusher takes (remote, branch, cwd) and returns (ok, output).
Pusher = Callable[[str, str, Path], "tuple[bool, str]"]


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(cwd),
                          capture_output=True, text=True)


def _require(res: subprocess.CompletedProcess, what: str) -> None:
    if res.returncode != 0:
        raise RuntimeError(f"{what} failed: {(res.stderr or res.stdout).strip()}")


def current_branch(cwd: Path = ROOT) -> str:
    res = _git(["rev-parse", "--abbrev-ref", "HEAD"], cwd)
    _require(res, "git rev-parse")
    return res.stdout.strip()


def commit_only(paths: list[Path], message: str, cwd: Path = ROOT) -> str:
    """Commit ONLY the given paths, even if other changes are staged.

    Uses `git commit -- <pathspec>` so the resulting commit's tree diff touches
    exactly those paths. Returns the new commit SHA.
    """
    spec = [str(p) for p in paths]
    for p in spec:
        _require(_git(["add", "--", p], cwd), f"git add {p}")
    _require(_git(["commit", "-m", message, "--", *spec], cwd), "git commit")
    res = _git(["rev-parse", "HEAD"], cwd)
    _require(res, "git rev-parse HEAD")
    return res.stdout.strip()


def commit_message_for(rec: dict) -> str:
    return (f"Publish prediction: {rec['season']} R{rec['round']} {rec['event']}\n\n"
            f"race_start_utc={rec.get('race_start_utc')}\n"
            f"made_at_utc={rec['made_at_utc']}\n"
            f"content_hash={rec['content_hash']}")


def _default_push(remote: str, branch: str, cwd: Path) -> "tuple[bool, str]":
    res = _git(["push", remote, branch], cwd)
    return res.returncode == 0, (res.stderr or res.stdout).strip()


def publish_commit_push(
    pred_path: Path,
    *,
    remote: str = "origin",
    branch: str | None = None,
    push: bool = True,
    pusher: Pusher | None = None,
    cwd: Path = ROOT,
    track_record_path: Path = TRACK_RECORD_PATH,
) -> dict:
    """Commit a freshly published prediction file and its track record.

    Returns a result dict with an `ok` flag. On any push failure `ok` is False
    and `status` says which push failed; the routine does not pretend success.
    """
    pred_path = Path(pred_path)
    rec = json.loads(pred_path.read_text(encoding="utf-8"))
    branch = branch or current_branch(cwd)
    do_push = pusher or _default_push
    result: dict = {
        "ok": False,
        "status": "started",
        "prediction_file": pred_path.name,
        "content_hash": rec.get("content_hash"),
        "prediction_commit": None,
        "track_record_commit": None,
        "pushes": [],
    }

    # 1. dedicated single-file commit for the prediction.
    result["prediction_commit"] = commit_only(
        [pred_path], commit_message_for(rec), cwd)

    # 2. push it.
    if push:
        ok, out = do_push(remote, branch, cwd)
        result["pushes"].append({"what": "prediction", "ok": ok, "output": out})
        if not ok:
            result["status"] = "push_failed_after_prediction_commit"
            return result

    # 3. regenerate TRACK_RECORD.md and commit it.
    write_track_record(track_record_path)
    # If nothing changed, git commit exits non-zero; treat "nothing to commit"
    # as a no-op rather than an error.
    add = _git(["add", "--", str(track_record_path)], cwd)
    _require(add, f"git add {track_record_path}")
    diff = _git(["diff", "--cached", "--quiet", "--", str(track_record_path)], cwd)
    if diff.returncode != 0:  # there is a staged change to commit
        result["track_record_commit"] = commit_only(
            [track_record_path],
            f"Update track record after {rec['season']} R{rec['round']} {rec['event']}",
            cwd)
        # 4. push the track record.
        if push:
            ok, out = do_push(remote, branch, cwd)
            result["pushes"].append({"what": "track_record", "ok": ok, "output": out})
            if not ok:
                result["status"] = "push_failed_after_track_record_commit"
                return result

    result["ok"] = True
    result["status"] = "pushed" if push else "committed_no_push"
    return result
