"""Two-stage pipeline: qualifying -> race.

predict_weekend() runs both stages: predict grid, substitute it into the race
features as F_GRID, then predict finishing order. This lets the race model run
without knowing the real grid — a genuine forecast you could publish on Thursday.

For evaluation we support both modes:
  - use_real_grid=True : isolates the race model's quality (grid is given).
  - use_real_grid=False: end-to-end realism (quali error propagates).
Reporting both is the honest way to show where error comes from.
"""
from __future__ import annotations

import pandas as pd

from f1grid import schema as S
from f1grid.model.quali_model import QualiModel
from f1grid.model.order_model import OrderModel


class TwoStagePipeline:
    def __init__(self):
        self.quali = QualiModel()
        self.race = OrderModel()

    def fit(self, train_feats: pd.DataFrame) -> "TwoStagePipeline":
        self.quali.fit(train_feats)
        self.race.fit(train_feats)
        return self

    def predict_weekend(self, race_feats: pd.DataFrame,
                        use_real_grid: bool = False) -> pd.DataFrame:
        feats = race_feats.copy()
        if use_real_grid:
            feats["predicted_grid"] = feats[S.F_GRID]
        else:
            q = self.quali.predict_grid(feats)
            feats = feats.merge(
                q[[S.DRIVER, "predicted_grid"]], on=S.DRIVER, how="left"
            )
            # Substitute predicted grid into the feature the race model reads.
            feats[S.F_GRID] = feats["predicted_grid"]

        order = self.race.predict_order(feats)
        return order
