"""App state: data + models loaded once at startup, shared across requests.

Same constraint as the Streamlit app: this is an inference-only service. It
reads pre-built artifacts (results cache + trained models) produced by running
`f1grid.data.ingest` + `f1grid.train` locally with internet access. If those
artifacts are missing, it falls back to synthetic demo data and labels every
response with `is_real_data: false` so a caller can never mistake a demo
response for a real one.
"""
from __future__ import annotations

import sys
from pathlib import Path
from functools import lru_cache

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from f1grid import schema as S  # noqa: E402
from f1grid.config import CONFIG, MODEL_DIR, EVAL_DIR, DATA_DIR  # noqa: E402
from f1grid.features.build import build_features  # noqa: E402
from f1grid.model import strategy_meter as _meter  # noqa: E402
from f1grid.model.quali_model import QualiModel  # noqa: E402
from f1grid.model.order_model import OrderModel  # noqa: E402
from f1grid.model.pipeline import TwoStagePipeline  # noqa: E402
from f1grid.model.panel import Scenario  # noqa: E402


class AppState:
    def __init__(self):
        self.results: pd.DataFrame | None = None
        self.is_real_data: bool = False
        self.feats: pd.DataFrame | None = None
        self.pipeline: TwoStagePipeline | None = None
        self.used_saved_models: bool = False
        self.scenario: Scenario | None = None
        self.laps: pd.DataFrame | None = None

    def load(self):
        try:
            from f1grid.data.ingest import load_results
            self.results = load_results()
            self.is_real_data = True
        except FileNotFoundError:
            from tests.synthetic import make_synthetic
            self.results = make_synthetic()
            self.is_real_data = False

        self.feats = build_features(self.results)

        # Lap data is optional: it is a large, gitignored cache that is absent in
        # a fresh clone / deployment. The strategy meter degrades to the results-
        # only signal (grid-to-finish divergence) when it is missing.
        laps_path = DATA_DIR / "laps.parquet"
        try:
            self.laps = pd.read_parquet(laps_path) if laps_path.exists() else None
        except Exception:
            self.laps = None

        quali_path = MODEL_DIR / "quali_model.joblib"
        race_path = MODEL_DIR / "race_model.joblib"
        pipe = TwoStagePipeline()
        if quali_path.exists() and race_path.exists():
            pipe.quali = QualiModel.load(quali_path)
            pipe.race = OrderModel.load(race_path)
            self.used_saved_models = True
        else:
            train_feats = self.feats[~self.feats[S.SEASON].isin(CONFIG.eval_seasons)]
            pipe.fit(train_feats)
            self.used_saved_models = False
        self.pipeline = pipe
        self.scenario = Scenario.from_results(self.results)
        return self

    def model_card_text(self) -> str | None:
        path = EVAL_DIR / "MODEL_CARD.md"
        return path.read_text(encoding="utf-8") if path.exists() else None

    def strategy_meter(self, season: int, round_no: int, event: str) -> dict:
        """The validated circuit strategy-disruption meter for a race, shown
        alongside the prediction. Built only from prior races; never fed into the
        model. Synthetic-fallback data has no real circuits, so it reports a
        no-history state."""
        if not self.is_real_data:
            return {"label": "Strategy complexity", "is_confidence": False,
                    "state": "no_history", "level": None, "score": None,
                    "reason": "Strategy meter needs real race history; this "
                              "response is synthetic demo data.",
                    "signals": {}, "components_used": []}
        return _meter.classify_from_artifact(
            self.results, self.laps, event, season, round_no)


@lru_cache(maxsize=1)
def get_state() -> AppState:
    return AppState().load()
