"""Validation that decides what the strategy meter is ALLOWED to be called.

Procedure (fixed, honest, nothing tuned on held-out data):
  1. Compute the meter score for every race 2023-2026 from prior-race data only.
  2. DESIGN the Low/Medium/High tertile thresholds on 2023-2024 ONLY. Freeze them.
  3. Get real per-race walk-forward prediction error (Spearman, MAE) from the
     production race model's honest evaluation.
  4. On HELD-OUT 2025, test the hypothesis: do High-disruption races have WORSE
     error (lower Spearman AND higher MAE) than Low-disruption races?
       - holds  -> label "Prediction confidence (strategy-based)".
       - fails  -> label "Strategy complexity" (no confidence claim anywhere).
  5. Report 2026 once.

The decision plus the frozen thresholds and the per-bucket numbers are written to
artifacts/eval/strategy_meter.json, which the app/API/publish path read so the UI
wording follows the evidence.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from f1grid.config import DATA_DIR, EVAL_DIR
from f1grid.data.ingest import load_results
from f1grid.features.build import build_features
from f1grid.model.evaluate import walk_forward
from f1grid.model import strategy_meter as SM
from f1grid import schema as S

VALIDATION_SEASONS = (2023, 2024, 2025, 2026)
DESIGN_SEASONS = (2023, 2024)
HELDOUT_SEASON = 2025


def _meter_table(results: pd.DataFrame, laps: pd.DataFrame,
                 seasons=VALIDATION_SEASONS) -> pd.DataFrame:
    rows = []
    for season in seasons:
        rr = results[results[S.SEASON] == season][[S.ROUND, S.EVENT]].drop_duplicates()
        for _, x in rr.iterrows():
            rnd, ev = int(x[S.ROUND]), x[S.EVENT]
            m = SM.meter_score(results, laps, ev, season, rnd)
            rows.append({"season": season, "round": rnd, "event": ev,
                         "has_history": m["has_history"], "score": m["score"]})
    return pd.DataFrame(rows)


def _bucket_stats(sub: pd.DataFrame) -> dict:
    out = {}
    for b in ("Low", "Medium", "High"):
        part = sub[sub["bucket"] == b]
        out[b] = {
            "n": int(len(part)),
            "mean_spearman": round(float(part["spearman"].mean()), 4) if len(part) else None,
            "mean_mae": round(float(part["mae_pos"].mean()), 4) if len(part) else None,
        }
    return out


def run_validation(results: pd.DataFrame | None = None,
                   laps: pd.DataFrame | None = None) -> dict:
    results = results if results is not None else load_results()
    if laps is None:
        laps = pd.read_parquet(DATA_DIR / "laps.parquet")

    meter = _meter_table(results, laps)
    design_scores = meter[(meter["season"].isin(DESIGN_SEASONS)) &
                          (meter["has_history"])]["score"].tolist()
    th = SM.design_thresholds(design_scores)

    rep = walk_forward(build_features(results), eval_seasons=list(VALIDATION_SEASONS))
    err = rep["model"][["season", "round", "event", "spearman", "mae_pos"]]

    df = meter.merge(err, on=["season", "round", "event"], how="inner")
    df = df[df["has_history"]].copy()
    df["bucket"] = df["score"].apply(lambda s: SM.bucket_for(s, th))

    design = _bucket_stats(df[df["season"].isin(DESIGN_SEASONS)])
    heldout = _bucket_stats(df[df["season"] == HELDOUT_SEASON])
    wf2026 = _bucket_stats(df[df["season"] == 2026])

    lo, hi = heldout["Low"], heldout["High"]
    holds = (
        lo["mean_spearman"] is not None and hi["mean_spearman"] is not None
        and hi["mean_spearman"] < lo["mean_spearman"]
        and hi["mean_mae"] > lo["mean_mae"]
    )
    label_mode = "confidence" if holds else "complexity"

    no_history = meter[~meter["has_history"]][["season", "round", "event"]]
    return {
        "t1": th["t1"], "t2": th["t2"], "n_design_races": th["n_design_races"],
        "hypothesis": "high-disruption races have worse error "
                      "(lower Spearman AND higher MAE) than low-disruption races",
        "held": bool(holds),
        "label_mode": label_mode,
        "decided_by": f"held-out {HELDOUT_SEASON} walk-forward",
        "buckets": {
            "design_2023_2024": design,
            "held_out_2025": heldout,
            "walk_forward_2026": wf2026,
        },
        "no_history_races": no_history.to_dict(orient="records"),
        "signal_scales": {"pit_spread": SM.PIT_SPREAD_SCALE,
                          "divergence": SM.DIVERGENCE_SCALE},
    }


def write_artifact(path: Path = SM.METER_ARTIFACT, result: dict | None = None) -> Path:
    result = result or run_validation()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    return path


if __name__ == "__main__":
    res = run_validation()
    p = write_artifact(result=res)
    print(f"label_mode = {res['label_mode']}  (held={res['held']})")
    print(f"thresholds t1={res['t1']:.4f} t2={res['t2']:.4f}")
    print("held-out 2025 buckets:")
    for b, v in res["buckets"]["held_out_2025"].items():
        print(f"  {b:6s} n={v['n']} spearman={v['mean_spearman']} mae={v['mean_mae']}")
    print(f"Wrote {p}")
