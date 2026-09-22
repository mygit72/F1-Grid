"""Run the full pipeline on synthetic data to prove it works offline."""
import sys
sys.path.insert(0, ".")

import numpy as np
from tests.synthetic import make_synthetic
from f1grid.features.build import build_features, assert_no_leakage
from f1grid.model.evaluate import walk_forward, summarize
from f1grid.model.order_model import OrderModel

print("1) generating synthetic results...")
results = make_synthetic()
print(f"   {len(results)} driver-rows across {results['season'].nunique()} seasons")

print("2) building leakage-free features...")
feats = build_features(results)
print(f"   {len(feats)} feature rows, {len(feats.columns)} cols")

print("3) leakage check...")
assert_no_leakage(results, feats)

print("4) walk-forward eval on 2025...")
report = walk_forward(feats, eval_seasons=(2025,))
summary = summarize(report)
print(summary.to_string(index=False))

print("5) feature importance (model trained on all but eval):")
train = feats[feats["season"] < 2025]
m = OrderModel().fit(train)
print(f"   backend: {m.backend}")
print(m.feature_importance().head(8).to_string())
