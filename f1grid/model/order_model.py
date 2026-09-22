"""Finishing-order model: an XGBoost ranker over per-race driver groups.

We frame full-order prediction as learning-to-rank: within each race (a "group"),
learn a score that orders drivers by finishing position. This is the natural
formulation for "predict the full order" and avoids pretending positions are
independent regression targets.

The model exposes predict_order(), which returns drivers sorted best->worst with
a model score, plus a derived rank. Probability estimates for podium/points are
produced separately by the Monte Carlo layer (predict/race.py).
"""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from f1grid.config import CONFIG
from f1grid import schema as S


def _native_paths(path):
    """Sibling paths for the native XGBoost booster (JSON) and the plain-JSON
    metadata (feature list + params). Given ``quali_model.joblib`` these are
    ``quali_model.xgb.json`` and ``quali_model.meta.json``."""
    path = Path(path)
    stem = path.with_suffix("")
    return (stem.with_name(stem.name + ".xgb.json"),
            stem.with_name(stem.name + ".meta.json"))

# Prefer XGBoost's learning-to-rank. Fall back to a sklearn regressor on the
# inverted-position target if xgboost isn't installed (e.g. offline sandbox).
# The fallback is functionally a pointwise ranker and lets the full pipeline run
# anywhere; production installs xgboost and gets the pairwise ranker.
try:
    import xgboost as xgb
    _HAVE_XGB = True
except ImportError:  # pragma: no cover
    from sklearn.ensemble import GradientBoostingRegressor
    _HAVE_XGB = False


class OrderModel:
    def __init__(self, params: dict | None = None, feature_columns=None):
        self.params = params or CONFIG.xgb_params
        self.model = None
        self.backend = "xgboost" if _HAVE_XGB else "sklearn_fallback"
        self.feature_columns = list(feature_columns) if feature_columns is not None \
            else list(S.FEATURE_COLUMNS)

    def _groups(self, feats: pd.DataFrame) -> np.ndarray:
        # group sizes per race, in the order rows appear (must be pre-sorted by race)
        return feats.groupby("race_id", sort=False).size().to_numpy()

    def fit(self, feats: pd.DataFrame) -> "OrderModel":
        feats = feats.sort_values(["race_id", S.FINISH]).reset_index(drop=True)
        X = feats[self.feature_columns].astype(float).fillna(0.0)
        # Relevance: higher = better finish. Invert position so P1 has top relevance.
        y = (CONFIG.grid_dnf_position + 1) - feats[S.FINISH].astype(int)
        if _HAVE_XGB:
            groups = self._groups(feats)
            self.model = xgb.XGBRanker(**self.params)
            self.model.fit(X, y, group=groups)
        else:
            self.model = GradientBoostingRegressor(
                n_estimators=self.params.get("n_estimators", 300),
                max_depth=self.params.get("max_depth", 5),
                learning_rate=self.params.get("learning_rate", 0.05),
                subsample=self.params.get("subsample", 0.85),
                random_state=self.params.get("random_state", 42),
            )
            self.model.fit(X, y)
        return self

    def score(self, feats: pd.DataFrame) -> np.ndarray:
        if self.model is None:
            raise RuntimeError("Model not fit.")
        X = feats[self.feature_columns].astype(float).fillna(0.0)
        return self.model.predict(X)

    def predict_order(self, race_feats: pd.DataFrame) -> pd.DataFrame:
        """One race in -> drivers ordered best->worst with predicted rank."""
        out = race_feats.copy()
        out["model_score"] = self.score(out)
        out = out.sort_values("model_score", ascending=False).reset_index(drop=True)
        out["predicted_position"] = np.arange(1, len(out) + 1)
        return out

    def feature_importance(self) -> pd.Series:
        if self.model is None:
            raise RuntimeError("Model not fit.")
        if _HAVE_XGB:
            booster = self.model.get_booster()
            gain = booster.get_score(importance_type="gain")
            idx = {f"f{i}": c for i, c in enumerate(self.feature_columns)}
            s = pd.Series({idx.get(k, k): v for k, v in gain.items()})
        else:
            s = pd.Series(self.model.feature_importances_, index=self.feature_columns)
        return s.reindex(self.feature_columns).fillna(0.0).sort_values(ascending=False)

    def save(self, path):
        # joblib blob: kept for backward compatibility and for the sklearn fallback.
        joblib.dump({"model": self.model, "features": self.feature_columns,
                     "params": self.params}, path)
        # Native XGBoost booster (version-portable, no pickle) + plain-JSON metadata.
        if self.backend == "xgboost" and self.model is not None:
            booster_p, meta_p = _native_paths(path)
            self.model.save_model(str(booster_p))
            meta_p.write_text(json.dumps({
                "features": list(self.feature_columns),
                "params": self.params,
                "backend": self.backend,
                "model_kind": "XGBRanker",
                "xgboost_version": xgb.__version__,
            }, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path) -> "OrderModel":
        # Prefer the native format: loading a booster from JSON does not unpickle a
        # class from a possibly-different library version, so it is robust across
        # versions and never emits XGBoost's cross-version warning.
        booster_p, meta_p = _native_paths(path)
        if _HAVE_XGB and booster_p.exists() and meta_p.exists():
            meta = json.loads(meta_p.read_text(encoding="utf-8"))
            m = cls(params=meta.get("params"))
            model = xgb.XGBRanker(**(meta.get("params") or {}))
            model.load_model(str(booster_p))
            m.model = model
            m.feature_columns = list(meta["features"])
            m.backend = "xgboost"
            return m
        blob = joblib.load(path)
        m = cls(params=blob["params"])
        m.model = blob["model"]
        m.feature_columns = blob["features"]
        return m
