"""Honest, leakage-free evaluation.

Walk-forward by race: for each race R in the eval window, train on every race that
occurred strictly before R, predict R, then score against R's real result. This is
the only fair way to evaluate a time series — random k-fold would let the model see
the future.

Metrics:
  - spearman: rank correlation between predicted and actual order (primary, since
    the target is the full order).
  - top1_acc: did we name the winner.
  - podium_acc: fraction of the real top-3 we placed in our predicted top-3.
  - mae_pos: mean absolute error of predicted vs actual finishing position.
We always report the same metrics for a GRID-ORDER BASELINE (predict the finishing
order = the starting grid). Beating that baseline is the bar that makes the model
worth anything; a model that can't is just re-reading qualifying.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from f1grid.config import CONFIG
from f1grid import schema as S
from f1grid.model.order_model import OrderModel


@dataclass
class RaceMetrics:
    season: int
    round: int
    event: str
    n_drivers: int
    spearman: float
    top1_acc: float
    podium_acc: float
    mae_pos: float


def _race_metrics(pred_order: pd.DataFrame) -> dict:
    """pred_order has predicted_position + true FINISH."""
    pred = pred_order["predicted_position"].to_numpy()
    true = pred_order[S.FINISH].to_numpy()

    rho = spearmanr(pred, true).statistic
    rho = 0.0 if np.isnan(rho) else float(rho)

    pred_winner = pred_order.loc[pred_order["predicted_position"] == 1, S.DRIVER].iloc[0]
    true_winner = pred_order.loc[pred_order[S.FINISH] == pred_order[S.FINISH].min(), S.DRIVER].iloc[0]
    top1 = float(pred_winner == true_winner)

    pred_top3 = set(pred_order.nsmallest(3, "predicted_position")[S.DRIVER])
    true_top3 = set(pred_order.nsmallest(3, S.FINISH)[S.DRIVER])
    podium = len(pred_top3 & true_top3) / 3.0

    mae = float(np.mean(np.abs(pred - true)))
    return {"spearman": rho, "top1_acc": top1, "podium_acc": podium, "mae_pos": mae}


def _grid_baseline_order(race_feats: pd.DataFrame) -> pd.DataFrame:
    out = race_feats.copy()
    out = out.sort_values(S.F_GRID, ascending=True).reset_index(drop=True)
    out["predicted_position"] = np.arange(1, len(out) + 1)
    return out


def walk_forward(feats: pd.DataFrame, eval_seasons=None, feature_columns=None) -> dict:
    eval_seasons = eval_seasons or CONFIG.eval_seasons
    feats = feats.sort_values(["race_id"]).reset_index(drop=True)

    eval_race_ids = (
        feats[feats[S.SEASON].isin(eval_seasons)]["race_id"].drop_duplicates().tolist()
    )

    model_rows, base_rows = [], []
    for rid in eval_race_ids:
        train = feats[feats["race_id"] < rid]
        test = feats[feats["race_id"] == rid].copy()
        if train["race_id"].nunique() < 5 or len(test) < 5:
            continue

        model = OrderModel(feature_columns=feature_columns).fit(train)
        pred = model.predict_order(test)
        m = _race_metrics(pred)

        base = _grid_baseline_order(test)
        bm = _race_metrics(base)

        meta = {
            "season": int(test[S.SEASON].iloc[0]),
            "round": int(test[S.ROUND].iloc[0]),
            "event": test[S.EVENT].iloc[0],
            "n_drivers": len(test),
        }
        model_rows.append(RaceMetrics(**meta, **m))
        base_rows.append(RaceMetrics(**meta, **bm))

    model_df = pd.DataFrame([asdict(r) for r in model_rows])
    base_df = pd.DataFrame([asdict(r) for r in base_rows])
    return {"model": model_df, "baseline": base_df}


def _order_metrics_from_baseline(order: pd.DataFrame, truth: pd.DataFrame) -> dict:
    """Score a baseline order (driver, predicted_position) against real finish."""
    merged = order.merge(truth[[S.DRIVER, S.FINISH]], on=S.DRIVER, how="inner")
    if len(merged) < 5:
        return {}
    return _race_metrics(merged)


def walk_forward_prequali_baselines(feats: pd.DataFrame, results: pd.DataFrame,
                                    eval_seasons=None) -> pd.DataFrame:
    """Walk-forward: the END-TO-END pipeline (predicted grid, i.e. what a
    pre-qualifying prediction really is) vs the two pre-qualifying baselines
    (championship standings, previous-race order). All three predict the same
    lineup per race and are scored against the same real result, so the columns
    are directly comparable. The existing grid-order comparison is untouched.
    """
    from f1grid.model.pipeline import TwoStagePipeline
    from f1grid.model import baselines as B

    eval_seasons = eval_seasons or CONFIG.eval_seasons
    feats = feats.sort_values(["race_id"]).reset_index(drop=True)
    eval_race_ids = (
        feats[feats[S.SEASON].isin(eval_seasons)]["race_id"].drop_duplicates().tolist()
    )
    pipe_rows, champ_rows, prev_rows = [], [], []
    for rid in eval_race_ids:
        train = feats[feats["race_id"] < rid]
        test = feats[feats["race_id"] == rid].copy()
        if train["race_id"].nunique() < 5 or len(test) < 5:
            continue
        season = int(test[S.SEASON].iloc[0])
        rnd = int(test[S.ROUND].iloc[0])
        lineup = test[S.DRIVER].tolist()

        pipe = TwoStagePipeline().fit(train)
        order = pipe.predict_weekend(test, use_real_grid=False)
        pm = _race_metrics(order)
        if pm:
            pipe_rows.append(pm)

        champ = B.championship_standings_order(results, season, rnd, lineup=lineup)
        cm = _order_metrics_from_baseline(champ, test)
        if cm:
            champ_rows.append(cm)

        prev = B.previous_race_order(results, season, rnd, lineup=lineup)
        vm = _order_metrics_from_baseline(prev, test)
        if vm:
            prev_rows.append(vm)

    def agg(rows, label):
        if not rows:
            return None
        df = pd.DataFrame(rows)
        return {"system": label, "races": len(df),
                **{k: float(df[k].mean()) for k in
                   ["spearman", "top1_acc", "podium_acc", "mae_pos"]}}

    out = [r for r in (
        agg(pipe_rows, "Full pipeline (predicted grid)"),
        agg(champ_rows, "Championship-standings baseline"),
        agg(prev_rows, "Previous-race baseline"),
    ) if r is not None]
    return pd.DataFrame(out)


def model_summary(feats: pd.DataFrame, eval_seasons, feature_columns=None) -> dict:
    """Walk-forward metrics for the F1Grid model with a given feature set."""
    rep = walk_forward(feats, eval_seasons=eval_seasons, feature_columns=feature_columns)
    s = summarize(rep)
    row = s[s["system"] == "F1Grid model"]
    if row.empty:
        return {}
    r = row.iloc[0]
    return {"races": int(r["races"]), "spearman": float(r["spearman"]),
            "top1_acc": float(r["top1_acc"]), "podium_acc": float(r["podium_acc"]),
            "mae_pos": float(r["mae_pos"])}


def summarize(report: dict) -> pd.DataFrame:
    def agg(df, label):
        return pd.Series({
            "system": label,
            "races": len(df),
            "spearman": df["spearman"].mean(),
            "top1_acc": df["top1_acc"].mean(),
            "podium_acc": df["podium_acc"].mean(),
            "mae_pos": df["mae_pos"].mean(),
        })
    out = pd.DataFrame([
        agg(report["model"], "F1Grid model"),
        agg(report["baseline"], "Grid-order baseline"),
    ])
    return out
