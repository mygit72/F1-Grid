"""2026 data spot-check (item 5).

Regenerates a by-hand-checkable table of every 2026 race in the results parquet:
round, event, winner, podium, and the number of classified finishers. Written to
artifacts/eval/DATA_SPOTCHECK_2026.md straight from the data (never hand-edited)
and also returned for tests. Flags anything provisional or odd (missing drivers, a
duplicate round, an unexpected classified count).

    python -m scripts.spotcheck_2026
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from f1grid.config import EVAL_DIR
from f1grid.data.ingest import load_results
from f1grid import schema as S

OUT_PATH = EVAL_DIR / "DATA_SPOTCHECK_2026.md"


def spotcheck(season: int = 2026, results: pd.DataFrame | None = None) -> pd.DataFrame:
    results = results if results is not None else load_results()
    rs = results[results[S.SEASON] == season]
    rows = []
    for rnd, g in rs.groupby(S.ROUND):
        g = g.sort_values(S.FINISH)
        classified = g[g[S.DNF] == 0]
        podium = g[S.DRIVER].head(3).tolist()
        rows.append({
            "round": int(rnd),
            "event": g[S.EVENT].iloc[0],
            "winner": g[S.DRIVER].iloc[0],
            "podium": ", ".join(podium),
            "classified": int(len(classified)),
            "entries": int(len(g)),
        })
    return pd.DataFrame(rows).sort_values("round").reset_index(drop=True)


def flags(df: pd.DataFrame) -> list[str]:
    out = []
    dup = df["round"][df["round"].duplicated()].tolist()
    if dup:
        out.append(f"DUPLICATE round(s): {dup}")
    rounds = df["round"].tolist()
    if rounds and rounds != list(range(rounds[0], rounds[0] + len(rounds))):
        out.append(f"NON-CONTIGUOUS rounds: {rounds}")
    entry_counts = df["entries"].unique().tolist()
    if len(entry_counts) > 1:
        out.append(f"INCONSISTENT entry counts across rounds: {sorted(entry_counts)}")
    low = df[df["classified"] < 10]
    if not low.empty:
        out.append("LOW classified count (<10): rounds "
                   f"{low['round'].tolist()} - possible provisional/partial data")
    if not out:
        out.append("No structural anomalies (contiguous rounds, consistent entry "
                   "counts, all classified counts within a plausible F1 range).")
    return out


def render(df: pd.DataFrame) -> str:
    lines = [
        "# 2026 data spot-check",
        "",
        "Generated from artifacts/data/race_results.parquet (not hand-edited). "
        "Check each row by hand against the official classification.",
        "",
        "| round | event | winner | podium | classified | entries |",
        "|---|---|---|---|---|---|",
    ]
    for _, r in df.iterrows():
        lines.append(f"| {r['round']} | {r['event']} | {r['winner']} | "
                     f"{r['podium']} | {r['classified']} | {r['entries']} |")
    lines += ["", "## Flags", ""]
    lines += [f"- {f}" for f in flags(df)]
    return "\n".join(lines) + "\n"


def main():
    df = spotcheck()
    text = render(df)
    OUT_PATH.write_text(text, encoding="utf-8")
    print(text)
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
