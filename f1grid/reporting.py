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

from f1grid.config import ROOT, PRED_DIR
from f1grid.score.scorer import track_record, SCORECARD
from f1grid.store.predictions import load_predictions

TRACK_RECORD_PATH = ROOT / "TRACK_RECORD.md"

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


def render_track_record(scorecard: Path = SCORECARD,
                        pred_dir: Path = PRED_DIR) -> str:
    lines = list(_HEADER)
    lines += _scored_table(scorecard)
    lines += _pending_table(scorecard, pred_dir)
    return "\n".join(lines).rstrip("\n") + "\n"


def write_track_record(path: Path = TRACK_RECORD_PATH,
                       scorecard: Path = SCORECARD,
                       pred_dir: Path = PRED_DIR) -> Path:
    path.write_text(render_track_record(scorecard, pred_dir), encoding="utf-8")
    return path


if __name__ == "__main__":
    p = write_track_record()
    print(f"Wrote {p}")
