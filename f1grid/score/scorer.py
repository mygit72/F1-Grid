"""Post-race scorer and rolling track record.

After a race runs, we pull the real classified result (from the same FastF1
results parquet) and grade the stored prediction that was made BEFORE the race.
We compute the same honest metrics as the offline eval (spearman, top1, podium,
mae) plus a grid-baseline comparison, and append to a public scorecard. Because
the prediction file is timestamped and immutable, the grade is verifiable.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from f1grid.config import EVAL_DIR
from f1grid import schema as S
from f1grid.store.predictions import latest_prediction
from f1grid.store import schedule as _schedule
from f1grid.model import baselines as _baselines

SCORECARD = EVAL_DIR / "scorecard.csv"


def _spearman(a, b) -> float:
    rho = spearmanr(a, b).statistic
    return 0.0 if np.isnan(rho) else float(rho)


def _baseline_for(rec: dict, season: int, round_no: int, results: pd.DataFrame,
                  merged: pd.DataFrame) -> dict:
    """Choose the fair baseline by WHEN the prediction was made (item 2).

    - pre-qualifying (made before the grid-setting quali session): grade against
      the pre-qualifying baselines (championship standings, previous race). We
      report the STRONGER of the two as the bar to beat.
    - post-qualifying: grade against the grid-order baseline, as before.

    `pre_qualifying` is read from the record; older records without it fall back
    to comparing made_at against the authoritative quali time, then default to
    post-qualifying (grid order) if quali time is unknown.
    """
    true = merged[S.FINISH].to_numpy()
    pre_q = rec.get("pre_qualifying")
    if pre_q is None:
        quali = _schedule.quali_start_utc(season, round_no)
        made_at = pd.to_datetime(rec.get("made_at_utc"), utc=True)
        if quali is not None and pd.notna(made_at):
            pre_q = made_at.to_pydatetime() < quali

    lineup = merged[S.DRIVER].tolist()
    if pre_q:
        champ = _baselines.championship_standings_order(results, season, round_no, lineup=lineup)
        prev = _baselines.previous_race_order(results, season, round_no, lineup=lineup)
        c = merged[[S.DRIVER, S.FINISH]].merge(champ, on=S.DRIVER, how="inner")
        p = merged[[S.DRIVER, S.FINISH]].merge(prev, on=S.DRIVER, how="inner")
        champ_rho = _spearman(c["predicted_position"], c[S.FINISH])
        prev_rho = _spearman(p["predicted_position"], p[S.FINISH])
        best = max(champ_rho, prev_rho)
        return {
            "baseline_used": "pre_qualifying",
            "baseline_spearman": round(best, 4),
            "baseline_champ_spearman": round(champ_rho, 4),
            "baseline_prevrace_spearman": round(prev_rho, 4),
        }
    # post-qualifying (or unknown): grid-order baseline, graded the same way.
    grid = merged[S.GRID].to_numpy()
    return {
        "baseline_used": "grid_order",
        "baseline_spearman": round(_spearman(grid, true), 4),
        "baseline_champ_spearman": None,
        "baseline_prevrace_spearman": None,
    }


def _grade(rec: dict, season: int, round_no: int, results: pd.DataFrame,
           actual: pd.DataFrame) -> dict:
    """Grade a prediction record against the real result, using the baseline that
    matches when the prediction was made."""
    pred_df = pd.DataFrame(rec["prediction"])[[S.DRIVER, "predicted_position"]]
    truth = actual[[S.DRIVER, S.FINISH, S.GRID]].copy()
    merged = pred_df.merge(truth, on=S.DRIVER, how="inner")
    if len(merged) < 5:
        return {}

    pred = merged["predicted_position"].to_numpy()
    true = merged[S.FINISH].to_numpy()

    rho = _spearman(pred, true)
    pred_winner = merged.loc[merged["predicted_position"] == 1, S.DRIVER].iloc[0]
    true_winner = merged.loc[merged[S.FINISH] == merged[S.FINISH].min(), S.DRIVER].iloc[0]
    top1 = float(pred_winner == true_winner)

    pred_top3 = set(merged.nsmallest(3, "predicted_position")[S.DRIVER])
    true_top3 = set(merged.nsmallest(3, S.FINISH)[S.DRIVER])
    podium = len(pred_top3 & true_top3) / 3.0
    mae = float(np.mean(np.abs(pred - true)))

    base = _baseline_for(rec, season, round_no, results, merged)

    return {
        "spearman": round(rho, 4),
        "top1_acc": top1,
        "podium_acc": round(podium, 4),
        "mae_pos": round(mae, 3),
        "beat_baseline": float(rho > base["baseline_spearman"]),
        "n_drivers": len(merged),
        **base,
    }


def score_race(season: int, round_no: int, results: pd.DataFrame,
               scorecard: Path = SCORECARD, pred_dir: Path | None = None) -> dict | None:
    """Grade the latest pre-race prediction for (season, round) against reality."""
    if pred_dir is None:
        rec = latest_prediction(season, round_no)
    else:
        rec = latest_prediction(season, round_no, pred_dir)
    if rec is None:
        print(f"No stored prediction for {season} R{round_no}.")
        return None

    actual = results[(results[S.SEASON] == season) & (results[S.ROUND] == round_no)]
    if actual.empty:
        print(f"No actual result yet for {season} R{round_no}.")
        return None

    grade = _grade(rec, season, round_no, results, actual)
    if not grade:
        return None

    row = {
        "season": season, "round": round_no, "event": rec["event"],
        "made_at_utc": rec["made_at_utc"], "data_cutoff": rec["data_cutoff"],
        "rain_prob": rec.get("rain_prob", 0.0), "content_hash": rec.get("content_hash"),
        **grade,
    }

    df = pd.DataFrame([row])
    if scorecard.exists():
        prev = pd.read_csv(scorecard, encoding="utf-8")
        # de-dup on (season, round, content_hash)
        df = pd.concat([prev, df], ignore_index=True).drop_duplicates(
            subset=["season", "round", "content_hash"], keep="last"
        )
    df.to_csv(scorecard, index=False, encoding="utf-8")
    return row


def track_record(scorecard: Path = SCORECARD) -> pd.DataFrame:
    """Rolling public track record across all scored races."""
    if not scorecard.exists():
        return pd.DataFrame()
    df = pd.read_csv(scorecard, encoding="utf-8").sort_values(["season", "round"])
    df["cum_top1"] = df["top1_acc"].expanding().mean().round(3)
    df["cum_podium"] = df["podium_acc"].expanding().mean().round(3)
    df["cum_beat_baseline"] = df["beat_baseline"].expanding().mean().round(3)
    return df
