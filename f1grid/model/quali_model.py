"""Qualifying model: predict the starting grid BEFORE the race.

This is stage 1 of the two-stage pipeline. It predicts qualifying order from
pre-qualifying signal only (pace/form/circuit history) — it must NOT use the
actual grid (that's what it's predicting) nor anything from the race.

The predicted grid then feeds the race model as its `grid_position` feature, so
the full system is: features -> [quali model] -> predicted grid -> [race model]
-> finishing order. We evaluate each stage alone and end-to-end.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from f1grid.config import CONFIG
from f1grid import schema as S

try:
    import xgboost as xgb
    _HAVE_XGB = True
except ImportError:  # pragma: no cover
    from sklearn.ensemble import GradientBoostingRegressor
    _HAVE_XGB = False

# Features the quali model is allowed to see. Note: NOT F_GRID (that's the target
# proxy) and nothing derived from the current race result.
QUALI_FEATURES = [
    S.F_FORM_FINISH,
    S.F_FORM_GRID,
    S.F_FORM_POINTS,
    S.F_DRV_PTS_TD,
    S.F_TEAM_PTS_TD,
    S.F_CIRCUIT_HIST,
    S.F_ROUND_NORM,
    S.F_PRIOR_EXP,
]


class QualiModel:
    def __init__(self, params: dict | None = None):
        self.params = params or CONFIG.xgb_params
        self.model = None
        self.backend = "xgboost" if _HAVE_XGB else "sklearn_fallback"
        self.feature_columns = list(QUALI_FEATURES)

    def _groups(self, feats: pd.DataFrame) -> np.ndarray:
        return feats.groupby("race_id", sort=False).size().to_numpy()

    def fit(self, feats: pd.DataFrame) -> "QualiModel":
        feats = feats.sort_values(["race_id", S.F_GRID]).reset_index(drop=True)
        X = feats[self.feature_columns].astype(float).fillna(0.0)
        # Target relevance: better grid (lower number) = higher relevance.
        y = (CONFIG.grid_dnf_position + 1) - feats[S.F_GRID].astype(int)
        if _HAVE_XGB:
            self.model = xgb.XGBRanker(**self.params)
            self.model.fit(X, y, group=self._groups(feats))
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

    def predict_grid(self, race_feats: pd.DataFrame) -> pd.DataFrame:
        """Return race_feats with a predicted_grid column (1..N)."""
        out = race_feats.copy()
        X = out[self.feature_columns].astype(float).fillna(0.0)
        out["_quali_score"] = self.model.predict(X)
        out = out.sort_values("_quali_score", ascending=False).reset_index(drop=True)
        out["predicted_grid"] = np.arange(1, len(out) + 1)
        return out

    def save(self, path):
        import joblib
        joblib.dump({"model": self.model, "features": self.feature_columns,
                     "params": self.params}, path)

    @classmethod
    def load(cls, path):
        import joblib
        blob = joblib.load(path)
        m = cls(params=blob["params"])
        m.model = blob["model"]
        m.feature_columns = blob["features"]
        return m
