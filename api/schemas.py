"""Pydantic response/request models — the API's public contract."""
from __future__ import annotations

from pydantic import BaseModel, Field


class RaceInfo(BaseModel):
    season: int
    round: int
    event: str


class DriverPrediction(BaseModel):
    driver: str
    team: str | None = None
    predicted_position: int
    win_prob: float | None = None
    podium_prob: float | None = None
    points_prob: float | None = None
    dnf_prob: float | None = None


class StrategyMeter(BaseModel):
    """Circuit strategy-disruption meter shown ALONGSIDE the prediction (never
    fed into the model). `label` is decided by held-out validation: "Strategy
    complexity" (a description, no confidence claim) unless the meter was shown
    to track prediction error out-of-sample, in which case it becomes "Prediction
    confidence (strategy-based)". `state` is "no_history" for new venues."""
    label: str
    is_confidence: bool
    state: str            # "ok" or "no_history"
    level: str | None = None   # Low / Medium / High, or null
    score: float | None = None
    reason: str
    components_used: list[str] = []


class PredictionResponse(BaseModel):
    season: int
    round: int
    event: str
    used_real_grid: bool
    rain_prob: float
    is_real_data: bool
    predictions: list[DriverPrediction]
    strategy_meter: StrategyMeter | None = None


class StrategyRequest(BaseModel):
    base_lap_time: float = Field(90.0, ge=60, le=140)
    total_laps: int = Field(57, ge=20, le=80)
    rain_prob: float = Field(0.0, ge=0.0, le=1.0)
    sc_lambda: float = Field(0.6, ge=0.0, le=3.0)
    strategies: dict[str, list[tuple[str, int]]]  # label -> [(compound, laps), ...]


class StrategyResult(BaseModel):
    label: str
    sequence: list[str]
    n_stops: int
    mean_time: float
    p10_time: float
    p90_time: float
    gap_to_best: float


class TrackRecordRow(BaseModel):
    season: int
    round: int
    event: str
    spearman: float
    top1_acc: float
    podium_acc: float
    mae_pos: float
    baseline_spearman: float
    beat_baseline: float
    cum_top1: float | None = None
    cum_podium: float | None = None
    cum_beat_baseline: float | None = None


class ScenarioOverride(BaseModel):
    team: str | None = None
    team_dials: dict[str, float] | None = None
    driver: str | None = None
    driver_dials: dict[str, float] | None = None
