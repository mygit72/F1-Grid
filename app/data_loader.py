"""Cached loaders for the app. Real artifacts (from `python -m f1grid.data.ingest`
+ `python -m f1grid.train` run locally with internet) are preferred. If they
don't exist yet — e.g. right after a fresh deploy before you've run training —
the app falls back to the synthetic fixture so it's never just a blank/broken
page, but it labels that state loudly everywhere in the UI.
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from f1grid import schema as S  # noqa: E402
from f1grid.config import CONFIG, MODEL_DIR, EVAL_DIR  # noqa: E402
from f1grid.features.build import build_features  # noqa: E402
from f1grid.model.quali_model import QualiModel  # noqa: E402
from f1grid.model.order_model import OrderModel  # noqa: E402
from f1grid.model.pipeline import TwoStagePipeline  # noqa: E402
from f1grid.model.panel import Scenario  # noqa: E402


@st.cache_data(show_spinner=False)
def load_results_cached() -> tuple[pd.DataFrame, bool]:
    """Returns (results, is_real). is_real=False means synthetic demo data."""
    try:
        from f1grid.data.ingest import load_results
        df = load_results()
        return df, True
    except FileNotFoundError:
        from tests.synthetic import make_synthetic
        return make_synthetic(), False


@st.cache_data(show_spinner=False)
def build_features_cached(results: pd.DataFrame) -> pd.DataFrame:
    return build_features(results)


@st.cache_resource(show_spinner=False)
def load_or_train_pipeline(_results_token: int, feats: pd.DataFrame,
                           eval_seasons: tuple[int, ...]) -> tuple[TwoStagePipeline, bool]:
    """Load saved models if present, else train in-process on the fly.
    Returns (pipeline, used_saved_models)."""
    quali_path = MODEL_DIR / "quali_model.joblib"
    race_path = MODEL_DIR / "race_model.joblib"
    pipe = TwoStagePipeline()
    if quali_path.exists() and race_path.exists():
        pipe.quali = QualiModel.load(quali_path)
        pipe.race = OrderModel.load(race_path)
        return pipe, True

    train_feats = feats[~feats[S.SEASON].isin(eval_seasons)]
    pipe.fit(train_feats)
    return pipe, False


@st.cache_data(show_spinner=False)
def load_model_card_text() -> str | None:
    path = EVAL_DIR / "MODEL_CARD.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return None


@st.cache_resource(show_spinner=False)
def build_scenario(_results_token: int, results: pd.DataFrame) -> Scenario:
    return Scenario.from_results(results)


def available_races(feats: pd.DataFrame) -> pd.DataFrame:
    return (
        feats[[S.SEASON, S.ROUND, S.EVENT]]
        .drop_duplicates()
        .sort_values([S.SEASON, S.ROUND])
        .reset_index(drop=True)
    )
