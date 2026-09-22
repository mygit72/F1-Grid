"""Deterministic public-track-record renderer.

Renders TRACK_RECORD.md from the immutable prediction store plus the post-race
scorecard. The output is a pure function of those files on disk: it contains no
wall-clock timestamp of its own, so regenerating it without new data produces a
byte-for-byte identical file. That property is what lets the publish routine
commit "regenerate + commit TRACK_RECORD.md" safely and lets a test assert the
generation is reproducible.

It never reads the fitted tyre curves, backtests, or any network source.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from f1grid.config import ROOT, PRED_DIR, PROV_DIR
from f1grid import schema as S
from f1grid.score.scorer import track_record, SCORECARD
from f1grid.store.predictions import load_predictions
from f1grid.provenance import read_provenance

TRACK_RECORD_PATH = ROOT / "TRACK_RECORD.md"
README_PATH = ROOT / "README.md"

README_TR_BEGIN = "<!-- F1GRID:TRACKRECORD:BEGIN -->"
README_TR_END = "<!-- F1GRID:TRACKRECORD:END -->"

_MEDALS = {1: "\U0001F947", 2: "\U0001F948", 3: "\U0001F949"}

_HEADER = [
    "# F1Grid public track record",
    "",
    "Auto-generated from the immutable, timestamped prediction store and the",
    "post-race scorecard. Every prediction listed here was committed to git",
    "BEFORE the race it forecasts started, so the grade is verifiable. Do not",
    "edit this file by hand: run the publish/score routine to regenerate it.",
    "",
]


def _scored_table(sc: Path) -> list[str]:
    tr = track_record(sc)
    if tr.empty:
        return ["## Scored races", "", "No races have been scored yet.", ""]
    cols = ["season", "round", "event", "made_at_utc", "spearman", "top1_acc",
            "podium_acc", "mae_pos", "baseline_spearman", "beat_baseline",
            "cum_top1", "cum_podium", "cum_beat_baseline"]
    cols = [c for c in cols if c in tr.columns]
    lines = ["## Scored races", "", "| " + " | ".join(cols) + " |",
             "| " + " | ".join("---" for _ in cols) + " |"]
    for _, r in tr.iterrows():
        lines.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
    lines.append("")
    return lines


def _pending_table(sc: Path, pred_dir: Path) -> list[str]:
    """Published predictions that have not been scored yet."""
    scored_keys = set()
    if sc.exists():
        prev = pd.read_csv(sc, encoding="utf-8")
        for _, r in prev.iterrows():
            scored_keys.add((int(r["season"]), int(r["round"]), str(r.get("content_hash"))))

    rows = []
    for rec in load_predictions(pred_dir=pred_dir):
        key = (int(rec["season"]), int(rec["round"]), str(rec.get("content_hash")))
        if key in scored_keys:
            continue
        rows.append(rec)
    rows.sort(key=lambda r: (int(r["season"]), int(r["round"]), r["made_at_utc"]))

    if not rows:
        return ["## Published, awaiting result", "",
                "No published predictions are awaiting a result.", ""]
    cols = ["season", "round", "event", "made_at_utc", "race_start_utc",
            "is_pre_race", "content_hash"]
    lines = ["## Published, awaiting result", "", "| " + " | ".join(cols) + " |",
             "| " + " | ".join("---" for _ in cols) + " |"]
    for rec in rows:
        lines.append("| " + " | ".join(str(rec.get(c)) for c in cols) + " |")
    lines.append("")
    return lines


def _provenance_section(pred_dir: Path, prov_dir: Path) -> list[str]:
    """Third-party, server-side proof links for each published prediction.

    A commit date is set locally and can be forged, so it is not proof. These
    links (GitHub Release created_at, Wayback snapshot timestamp, PushEvent) are
    timestamps a third party controls. Rendered from the provenance sidecars.
    """
    recs = sorted(load_predictions(pred_dir=pred_dir),
                  key=lambda r: (int(r["season"]), int(r["round"]), r["made_at_utc"]))
    lines = ["## Verifiable provenance (third-party server timestamps)", "",
             "The commit date alone is NOT proof: it is set by the committer's",
             "machine. Proof is the server-side timestamps below, each of which",
             "must predate the race start.", ""]
    any_rows = False
    for rec in recs:
        path = rec.get("_path")
        if not path:
            continue
        data = read_provenance(Path(path), prov_dir)
        if not data:
            continue
        any_rows = True
        rel = data.get("release") or {}
        wb = data.get("wayback") or {}
        lines.append(f"### {rec['season']} R{rec['round']} {rec['event']}")
        lines.append("")
        lines.append(f"- Prediction file: `{data.get('prediction_file')}` "
                     f"(content_hash `{data.get('content_hash')}`)")
        lines.append(f"- Race start (UTC): {data.get('race_start_utc')}")
        if rel:
            lines.append(f"- GitHub Release: {rel.get('url')} "
                         f"(created_at {rel.get('created_at')}, "
                         f"published_at {rel.get('published_at')})")
        elif data.get("release_error"):
            lines.append(f"- GitHub Release: NOT AVAILABLE ({data['release_error']})")
        if wb:
            lines.append(f"- Wayback snapshot: {wb.get('snapshot_url')} "
                         f"(timestamp {wb.get('timestamp')})")
        elif data.get("wayback_error"):
            lines.append(f"- Wayback snapshot: NOT AVAILABLE ({data['wayback_error']})")
        if data.get("push_event_created_at"):
            lines.append(f"- PushEvent created_at: {data['push_event_created_at']} "
                         f"(supporting, short-lived)")
        lines.append(f"- Commit (date is NOT proof): {data.get('commit_sha')}")
        lines.append("")
    if not any_rows:
        lines.append("No provenance records yet.")
        lines.append("")
    return lines


def render_track_record(scorecard: Path = SCORECARD,
                        pred_dir: Path = PRED_DIR,
                        prov_dir: Path = PROV_DIR) -> str:
    lines = list(_HEADER)
    lines += _scored_table(scorecard)
    lines += _pending_table(scorecard, pred_dir)
    lines += _provenance_section(pred_dir, prov_dir)
    return "\n".join(lines).rstrip("\n") + "\n"


def write_track_record(path: Path = TRACK_RECORD_PATH,
                       scorecard: Path = SCORECARD,
                       pred_dir: Path = PRED_DIR,
                       prov_dir: Path = PROV_DIR) -> Path:
    path.write_text(render_track_record(scorecard, pred_dir, prov_dir),
                    encoding="utf-8")
    return path


def _scorecard_index(scorecard: Path) -> dict:
    idx: dict = {}
    if scorecard.exists():
        df = pd.read_csv(scorecard, encoding="utf-8")
        for _, r in df.iterrows():
            idx[(int(r["season"]), int(r["round"]))] = r.to_dict()
    return idx


def _podium_str(by_pos: dict) -> str:
    parts = [f"{_MEDALS[p]} {by_pos[p]}" for p in (1, 2, 3) if p in by_pos]
    return " ".join(parts) if parts else "-"


def _predicted_podium(rec: dict) -> dict:
    order = sorted(rec["prediction"], key=lambda r: r["predicted_position"])
    return {int(r["predicted_position"]): r["driver"] for r in order[:3]}


def _actual_podium(results, season: int, round_no: int) -> dict | None:
    if results is None:
        return None
    r = results[(results[S.SEASON] == season) & (results[S.ROUND] == round_no)]
    if r.empty:
        return None
    top = r.nsmallest(3, S.FINISH)
    return {int(row[S.FINISH]): row[S.DRIVER] for _, row in top.iterrows()}


def render_readme_track_record(scorecard: Path = SCORECARD,
                               pred_dir: Path = PRED_DIR,
                               prov_dir: Path = PROV_DIR,
                               results=None) -> str:
    """The README "Track record" section (markdown between its sentinels).

    One row per published race: predicted podium (medals), actual podium (medals)
    or "pending", podium hits, whether the baseline was beaten, and links to the
    GitHub Release and the Wayback snapshot. Ends with a running summary that
    claims nothing beyond the graded races. Pure function of the store + scorecard
    (+ the real results parquet, read only when a graded race needs its podium)."""
    recs = sorted(load_predictions(pred_dir=pred_dir),
                  key=lambda r: (int(r["season"]), int(r["round"]), r["made_at_utc"]))
    sc = _scorecard_index(scorecard)
    if results is None and any((int(r["season"]), int(r["round"])) in sc for r in recs):
        from f1grid.data.ingest import load_results
        results = load_results()

    L = ["## Track record", "",
         "Generated from the immutable, timestamped prediction store and the",
         "post-race scorecard (the same source as TRACK_RECORD.md). Actual podiums",
         "come from the real FastF1 result once the race has run. Regenerated on",
         "every publish and score; do not edit by hand.", ""]
    header = ["Race", "Predicted podium", "Actual podium", "Podium hits",
              "Beat baseline", "Links"]
    L.append("| " + " | ".join(header) + " |")
    L.append("| " + " | ".join("---" for _ in header) + " |")

    graded = 0
    total_hits = 0
    beat = 0
    for rec in recs:
        s, rd = int(rec["season"]), int(rec["round"])
        pred_pod = _podium_str(_predicted_podium(rec))
        prov = read_provenance(Path(rec["_path"]), prov_dir) if rec.get("_path") else None
        links = []
        if prov:
            rel = (prov.get("release") or {}).get("url")
            wb = (prov.get("wayback") or {}).get("snapshot_url")
            if rel:
                links.append(f"[release]({rel})")
            if wb:
                links.append(f"[wayback]({wb})")
        links_str = " ".join(links) if links else "-"

        if (s, rd) in sc:
            graded += 1
            row = sc[(s, rd)]
            act = _podium_str(_actual_podium(results, s, rd) or {})
            hits = int(round(float(row.get("podium_acc", 0.0)) * 3))
            total_hits += hits
            bb = row.get("beat_baseline") in (1, 1.0, True)
            beat += 1 if bb else 0
            hits_str, beat_str = f"{hits}/3", ("YES" if bb else "NO")
        else:
            act, hits_str, beat_str = "pending", "pending", "pending"

        L.append(f"| {s} R{rd} {rec['event']} | {pred_pod} | {act} | "
                 f"{hits_str} | {beat_str} | {links_str} |")

    L.append("")
    L.append(f"Summary: {graded} race(s) graded, {total_hits} podium pick(s) "
             f"correct across them, baseline beaten in {beat} of {graded} graded "
             f"race(s).")
    return "\n".join(L).strip("\n")


def update_readme_track_record(path: Path = README_PATH,
                               scorecard: Path = SCORECARD,
                               pred_dir: Path = PRED_DIR,
                               prov_dir: Path = PROV_DIR,
                               results=None) -> Path:
    """Insert or replace the README track-record section idempotently."""
    section = render_readme_track_record(scorecard, pred_dir, prov_dir, results)
    block = f"{README_TR_BEGIN}\n{section}\n{README_TR_END}"
    text = path.read_text(encoding="utf-8")
    if README_TR_BEGIN in text and README_TR_END in text:
        pre = text[:text.index(README_TR_BEGIN)]
        post = text[text.index(README_TR_END) + len(README_TR_END):]
        new = pre + block + post
    else:
        anchor = "\n## Architecture"
        if anchor in text:
            i = text.index(anchor)
            new = text[:i] + "\n" + block + "\n" + text[i:]
        else:
            new = text.rstrip("\n") + "\n\n" + block + "\n"
    path.write_text(new, encoding="utf-8")
    return path


if __name__ == "__main__":
    p = write_track_record()
    print(f"Wrote {p}")
    r = update_readme_track_record()
    print(f"Updated {r}")
