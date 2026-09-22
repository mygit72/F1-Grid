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

from f1grid.config import ROOT, PROV_DIR
from f1grid.reporting import (write_track_record, TRACK_RECORD_PATH,
                              update_readme_track_record, README_PATH)
from f1grid import provenance as prov
from f1grid import release_notes as RN

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
    repo: str | None = None,
    remote: str = "origin",
    branch: str | None = None,
    push: bool = True,
    pusher: Pusher | None = None,
    cwd: Path = ROOT,
    track_record_path: Path = TRACK_RECORD_PATH,
    readme_path: Path | None = None,
    collect_provenance: bool = True,
    prov_dir: Path = PROV_DIR,
    gh: str | None = None,
    do_wayback: bool = True,
) -> dict:
    """Commit a freshly published prediction file, gather third-party proof, and
    commit the updated track record.

    Flow: commit ONLY the prediction file, push, then (once it is on GitHub)
    collect server-side provenance (GitHub Release, Wayback snapshot, PushEvent)
    into a sidecar, regenerate TRACK_RECORD.md with the proof links, and commit +
    push the track record and sidecar together.

    Returns a result dict with an `ok` flag. On any push failure `ok` is False and
    `status` says which push failed; the routine never pretends success. The
    immutable prediction file is never modified: proof lives in a sidecar.
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
        "provenance": None,
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

    # 3. collect third-party, server-side proof now that the file is on GitHub.
    committed_paths = [track_record_path]
    if collect_provenance and repo:
        data = prov.collect_provenance(
            repo, pred_path, rec, result["prediction_commit"],
            branch=branch, gh=gh, do_wayback=do_wayback, prov_dir=prov_dir)
        result["provenance"] = data
        committed_paths.append(prov.sidecar_path(pred_path, prov_dir))

        # 3b. render medal-style notes onto the release GitHub just created. The
        # attached asset (the immutable prediction file) is never touched: only
        # the release description is set. Non-fatal, recorded like the proofs.
        if data.get("release") and not data.get("release_error"):
            try:
                RN.set_prediction_notes_on_release(repo, rec, pred_path.name, gh=gh)
                result["release_notes"] = {"ok": True}
            except Exception as e:  # noqa: BLE001 - record, do not fake
                result["release_notes"] = {"ok": False, "error": str(e)}

    # 4. regenerate TRACK_RECORD.md (with proof links) and commit it + sidecar,
    #    plus the README track-record section when a README path is given.
    write_track_record(track_record_path)
    if readme_path is not None:
        update_readme_track_record(readme_path)
        committed_paths.append(readme_path)
    spec = [str(p) for p in committed_paths]
    for s in spec:
        _require(_git(["add", "--", s], cwd), f"git add {s}")
    diff = _git(["diff", "--cached", "--quiet", "--", *spec], cwd)
    if diff.returncode != 0:  # there is a staged change to commit
        result["track_record_commit"] = commit_only(
            committed_paths,
            f"Update track record and provenance after "
            f"{rec['season']} R{rec['round']} {rec['event']}",
            cwd)
        # 5. push the track record + sidecar.
        if push:
            ok, out = do_push(remote, branch, cwd)
            result["pushes"].append({"what": "track_record", "ok": ok, "output": out})
            if not ok:
                result["status"] = "push_failed_after_track_record_commit"
                return result

    result["ok"] = True
    result["status"] = "pushed" if push else "committed_no_push"
    return result


def finalize_after_score(
    repo: str | None,
    scored_rows: list[dict],
    results,
    *,
    remote: str = "origin",
    branch: str | None = None,
    push: bool = True,
    pusher: Pusher | None = None,
    cwd: Path = ROOT,
    track_record_path: Path = TRACK_RECORD_PATH,
    readme_path: Path = README_PATH,
    gh: str | None = None,
    do_release: bool = True,
    dry_run_release: bool = False,
) -> dict:
    """After grading, append a "Result" section to each graded race's release and
    regenerate the reports (TRACK_RECORD.md + README track record), then commit and
    push them.

    `scored_rows` is the list of grade dicts the scorer returned (each carries
    season/round and the metrics). Appending a result never rewrites the release's
    prediction block (release_notes.append_result_block asserts that). Set
    `dry_run_release=True` to render the new bodies without editing anything on
    GitHub. A failed push is reported, never faked.
    """
    from f1grid.store.predictions import latest_prediction
    from f1grid import schema as S

    branch = branch or current_branch(cwd)
    do_push = pusher or _default_push
    result: dict = {"ok": False, "status": "started", "releases": [],
                    "report_commit": None, "pushes": []}

    if do_release and repo:
        for grade in scored_rows:
            s, rd = int(grade["season"]), int(grade["round"])
            rec = latest_prediction(s, rd)
            if rec is None:
                result["releases"].append({"race": f"{s} R{rd}", "ok": False,
                                           "error": "no stored prediction"})
                continue
            a = results[(results[S.SEASON] == s) & (results[S.ROUND] == rd)]
            a = a.sort_values(S.FINISH)
            actual_order = [{"driver": r[S.DRIVER], "finish": int(r[S.FINISH]),
                             "team": r.get(S.TEAM) if hasattr(r, "get") else None}
                            for _, r in a.iterrows()]
            try:
                RN.add_result_section_to_release(
                    repo, rec, grade, actual_order, gh=gh, dry_run=dry_run_release)
                result["releases"].append({"race": f"{s} R{rd}", "ok": True,
                                           "dry_run": dry_run_release})
            except Exception as e:  # noqa: BLE001 - record, do not fake
                result["releases"].append({"race": f"{s} R{rd}", "ok": False,
                                           "error": str(e)})

    # Regenerate both reports from the store + updated scorecard.
    write_track_record(track_record_path)
    update_readme_track_record(readme_path)

    committed = [track_record_path, readme_path]
    for c in committed:
        _require(_git(["add", "--", str(c)], cwd), f"git add {c}")
    diff = _git(["diff", "--cached", "--quiet", "--", *[str(c) for c in committed]], cwd)
    if diff.returncode != 0:
        result["report_commit"] = commit_only(
            committed, "Update track record and README after scoring", cwd)
        if push:
            ok, out = do_push(remote, branch, cwd)
            result["pushes"].append({"what": "reports", "ok": ok, "output": out})
            if not ok:
                result["status"] = "push_failed_after_report_commit"
                return result

    result["ok"] = True
    result["status"] = "pushed" if push else "committed_no_push"
    return result
