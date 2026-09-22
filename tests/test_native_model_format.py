"""Item 1: pinned versions + native XGBoost format.

Verifies two things about the saved serving models:

  * loading them emits NO warning (in particular not XGBoost's cross-version
    "loading a pickled model from a different version" warning), and
  * the native-JSON booster produces predictions that EXACTLY match the ones
    from the joblib-pickled booster, on several real races.

The native format is version-portable (no unpickling), so a deploy platform that
installs a newer XGBoost still loads the model without a warning and without
changing a single prediction.
"""
from __future__ import annotations

import warnings

import numpy as np
import pytest

from f1grid.config import MODEL_DIR
from f1grid import schema as S
from f1grid.model.quali_model import QualiModel
from f1grid.model.order_model import OrderModel, _native_paths

xgb = pytest.importorskip("xgboost")

import joblib  # noqa: E402

QP = MODEL_DIR / "quali_model.joblib"
RP = MODEL_DIR / "race_model.joblib"

MODELS = [(QP, QualiModel), (RP, OrderModel)]


def _joblib_loaded(cls, path):
    """Force the pickled path, ignoring the native files."""
    blob = joblib.load(path)
    m = cls(params=blob["params"])
    m.model = blob["model"]
    m.feature_columns = blob["features"]
    return m


def test_native_files_exist_alongside_joblib():
    for path, _ in MODELS:
        booster_p, meta_p = _native_paths(path)
        assert booster_p.exists(), f"missing native booster {booster_p}"
        assert meta_p.exists(), f"missing metadata sidecar {meta_p}"


@pytest.mark.parametrize("path,cls", MODELS)
def test_load_emits_no_version_warning(path, cls):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        cls.load(path)  # prefers native
    version_warnings = [
        str(w.message) for w in caught
        if "version" in str(w.message).lower() or "pickle" in str(w.message).lower()
    ]
    assert not version_warnings, f"unexpected version warning(s): {version_warnings}"


def test_native_predictions_exactly_match_joblib_on_real_races():
    from f1grid.data.ingest import load_results
    from f1grid.features.build import build_features

    feats = build_features(load_results())
    seasons = sorted(feats[S.SEASON].unique().tolist())
    target = 2025 if 2025 in seasons else seasons[-1]
    race_ids = list(dict.fromkeys(
        feats[feats[S.SEASON] == target]["race_id"].tolist()))[:6]
    assert race_ids, "no real races available to compare"

    pairs = [
        (_joblib_loaded(QualiModel, QP), QualiModel.load(QP)),
        (_joblib_loaded(OrderModel, RP), OrderModel.load(RP)),
    ]

    checked = 0
    for rid in race_ids:
        rf = feats[feats["race_id"] == rid]
        if rf.empty:
            continue
        checked += 1
        for m_joblib, m_native in pairs:
            X = rf[m_joblib.feature_columns].astype(float).fillna(0.0)
            s_joblib = np.asarray(m_joblib.model.predict(X), dtype=np.float64)
            s_native = np.asarray(m_native.model.predict(X), dtype=np.float64)
            # EXACT equality, not approximate.
            assert np.array_equal(s_joblib, s_native), (
                f"native != joblib for race {rid}: "
                f"max|diff|={np.max(np.abs(s_joblib - s_native)):.3e}")
    assert checked >= 3, f"expected several real races, checked only {checked}"
