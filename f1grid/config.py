"""Central configuration. One place to change seasons, paths, and model knobs."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "artifacts" / "data"          # cached raw + feature parquet
MODEL_DIR = ROOT / "artifacts" / "models"        # serialized models
PRED_DIR = ROOT / "artifacts" / "predictions"    # PUBLIC immutable pre-race predictions
PROV_DIR = ROOT / "artifacts" / "provenance"     # third-party proof sidecars (release/wayback/push)
BACKTEST_DIR = ROOT / "artifacts" / "backtests"  # retroactive/backtest predictions (NEVER public)
EVAL_DIR = ROOT / "artifacts" / "eval"           # eval reports / plots
FASTF1_CACHE = ROOT / "artifacts" / "fastf1_cache"

# Authoritative race-start schedule (season, round, event, race_start_utc) written
# by data.ingest. The store uses this to decide whether a prediction is genuinely
# pre-race; it is the single source of truth a caller cannot forge.
SCHEDULE_PARQUET = DATA_DIR / "schedule.parquet"

for _p in (DATA_DIR, MODEL_DIR, PRED_DIR, PROV_DIR, BACKTEST_DIR, EVAL_DIR, FASTF1_CACHE):
    _p.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class Config:
    # Seasons to pull for training history. FastF1 has reliable data from 2018+.
    train_seasons: tuple[int, ...] = (2019, 2020, 2021, 2022, 2023, 2024)
    # Season(s) held out for honest out-of-sample evaluation.
    eval_seasons: tuple[int, ...] = (2025,)

    # Rolling-form window: how many of a driver's most recent races to aggregate.
    form_window: int = 5

    # Minimum prior races a (season) must have before we trust season-to-date
    # team features; earlier rounds fall back to prior-season priors.
    min_prior_rounds: int = 1

    grid_dnf_position: int = 21  # sentinel finishing position for DNF / DNS

    xgb_params: dict = field(default_factory=lambda: {
        "objective": "rank:pairwise",
        "n_estimators": 400,
        "max_depth": 5,
        "learning_rate": 0.05,
        "subsample": 0.85,
        "colsample_bytree": 0.85,
        "min_child_weight": 3,
        "reg_lambda": 1.5,
        "random_state": 42,
        "n_jobs": -1,
    })

    random_state: int = 42


CONFIG = Config()
