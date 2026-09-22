"""F1Grid API.

Run locally:
    uvicorn api.main:app --reload --port 8000
Docs at http://localhost:8000/docs

This mirrors the Streamlit app's functionality as a proper backend, matching
the FastAPI/Docker/CI stack described in the README. Same honesty rules apply:
inference-only, reads pre-built artifacts, labels synthetic-fallback data.
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from f1grid import schema as S
from f1grid.runtime import is_deployed, DEPLOYED_REFUSAL, cors_allowed_origins
from f1grid.model.montecarlo import monte_carlo_outcomes
from f1grid.model.strategy_sim import compare_strategies, StintPlan
from f1grid.store.predictions import save_prediction, RetroactivePredictionError
from f1grid.score.scorer import score_race as _score_race, track_record as _track_record

from api.state import get_state
from api.schemas import (
    RaceInfo, PredictionResponse, DriverPrediction,
    StrategyRequest, StrategyResult, TrackRecordRow, ScenarioOverride,
    StrategyMeter,
)

app = FastAPI(
    title="F1Grid API",
    description=(
        "Leakage-free, walk-forward-evaluated Formula 1 prediction engine. "
        "See /about for the methodology and honesty guarantees."
    ),
    version="0.1.0",
)
# Allow only explicitly trusted origins (never a wildcard): the front-end origin
# set via F1GRID_CORS_ORIGINS on a deployment, plus local-dev defaults.
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_allowed_origins(),
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"name": "F1Grid API", "docs": "/docs", "about": "/about"}


@app.get("/about")
def about():
    state = get_state()
    return {
        "is_real_data": state.is_real_data,
        "used_saved_models": state.used_saved_models,
        "race_model_backend": state.pipeline.race.backend,
        "model_card": state.model_card_text(),
        "principle": (
            "A feature describing a race may only use information available "
            "before that race starts. All evaluation is walk-forward and always "
            "reported alongside a grid-order baseline."
        ),
    }


@app.get("/races", response_model=list[RaceInfo])
def list_races(season: int | None = Query(None)):
    state = get_state()
    races = state.feats[[S.SEASON, S.ROUND, S.EVENT]].drop_duplicates()
    if season is not None:
        races = races[races[S.SEASON] == season]
    races = races.sort_values([S.SEASON, S.ROUND])
    return [
        RaceInfo(season=int(r[S.SEASON]), round=int(r[S.ROUND]), event=r[S.EVENT])
        for _, r in races.iterrows()
    ]


@app.get("/predictions/{season}/{round_no}", response_model=PredictionResponse)
def get_prediction(
    season: int, round_no: int,
    rain_prob: float = Query(0.0, ge=0.0, le=1.0),
    use_real_grid: bool = Query(False),
):
    state = get_state()
    race_feats = state.feats[
        (state.feats[S.SEASON] == season) & (state.feats[S.ROUND] == round_no)
    ].copy()
    if race_feats.empty:
        raise HTTPException(404, f"No race found for season={season} round={round_no}")

    order = state.pipeline.predict_weekend(race_feats, use_real_grid=use_real_grid)
    order["wet_skill"] = order.get("wet_skill", 0.5)
    mc = monte_carlo_outcomes(order, rain_prob=rain_prob, n_sims=3000)
    merged = order.merge(
        mc[[S.DRIVER, "win_prob", "podium_prob", "points_prob", "dnf_prob"]],
        on=S.DRIVER,
    ).sort_values("predicted_position")

    event = race_feats[S.EVENT].iloc[0]
    preds = [
        DriverPrediction(
            driver=r[S.DRIVER], team=r.get(S.TEAM),
            predicted_position=int(r["predicted_position"]),
            win_prob=round(float(r["win_prob"]), 4),
            podium_prob=round(float(r["podium_prob"]), 4),
            points_prob=round(float(r["points_prob"]), 4),
            dnf_prob=round(float(r["dnf_prob"]), 4),
        )
        for _, r in merged.iterrows()
    ]
    meter = state.strategy_meter(season, round_no, event)
    return PredictionResponse(
        season=season, round=round_no, event=event, used_real_grid=use_real_grid,
        rain_prob=rain_prob, is_real_data=state.is_real_data, predictions=preds,
        strategy_meter=StrategyMeter(
            label=meter["label"], is_confidence=meter["is_confidence"],
            state=meter["state"], level=meter.get("level"),
            score=meter.get("score"), reason=meter["reason"],
            components_used=meter.get("components_used", []),
        ),
    )


@app.post("/predictions/{season}/{round_no}/publish")
def publish_prediction(
    season: int, round_no: int,
    rain_prob: float = Query(0.0, ge=0.0, le=1.0),
    use_real_grid: bool = Query(False),
    backtest: bool = Query(False, description="Store in the separate backtest "
                           "archive (never enters the public track record)."),
):
    """Writes the current prediction to an immutable, timestamped file.

    HARD BOUNDARY: a prediction can only enter the PUBLIC track record if it is
    made before the race starts. The store enforces this authoritatively, so a
    request for a race that has already run is refused here (HTTP 409) no matter
    how it is called. Pass backtest=true to store it in the separate, clearly
    labelled backtest archive that the public track record never reads.

    In deployment mode this write action is refused (HTTP 403): a container's
    storage is ephemeral and publicly reachable, so publishing stays a local CLI
    + git action only.
    """
    if is_deployed():
        raise HTTPException(403, DEPLOYED_REFUSAL)
    state = get_state()
    race_feats = state.feats[
        (state.feats[S.SEASON] == season) & (state.feats[S.ROUND] == round_no)
    ].copy()
    if race_feats.empty:
        raise HTTPException(404, f"No race found for season={season} round={round_no}")

    order = state.pipeline.predict_weekend(race_feats, use_real_grid=use_real_grid)
    order["wet_skill"] = order.get("wet_skill", 0.5)
    mc = monte_carlo_outcomes(order, rain_prob=rain_prob, n_sims=3000)
    merged = order.merge(
        mc[[S.DRIVER, "win_prob", "podium_prob", "points_prob", "dnf_prob"]],
        on=S.DRIVER,
    )
    event = race_feats[S.EVENT].iloc[0]
    meter = state.strategy_meter(season, round_no, event)
    try:
        path = save_prediction(
            season, round_no, event, merged,
            data_cutoff=f"as of {season} R{round_no-1}", rain_prob=rain_prob,
            backtest=backtest,
            model_meta={"backend": state.pipeline.race.backend,
                       "used_saved_models": state.used_saved_models},
            strategy_meter=meter,
        )
    except RetroactivePredictionError as e:
        raise HTTPException(409, str(e))
    return {"published": True, "backtest": backtest, "file": str(path)}


@app.post("/predictions/{season}/{round_no}/score")
def score_prediction(season: int, round_no: int):
    """Grades the latest published prediction against the real result, if known.

    Refused in deployment mode (HTTP 403): scoring writes to the ephemeral
    public scorecard and must stay a local CLI + git action.
    """
    if is_deployed():
        raise HTTPException(403, DEPLOYED_REFUSAL)
    state = get_state()
    row = _score_race(season, round_no, state.results)
    if row is None:
        raise HTTPException(
            404, "No stored prediction and/or no real result yet for this race."
        )
    return row


@app.get("/track-record", response_model=list[TrackRecordRow])
def track_record():
    df = _track_record()
    if df.empty:
        return []
    return [TrackRecordRow(**row) for row in df.to_dict(orient="records")]


@app.post("/strategy/compare", response_model=list[StrategyResult])
def compare_strategy(req: StrategyRequest):
    candidates = {
        label: [StintPlan(c, l) for c, l in stints]
        for label, stints in req.strategies.items()
    }
    results = compare_strategies(
        req.base_lap_time, req.total_laps, candidates,
        rain_prob=req.rain_prob, sc_lambda=req.sc_lambda, n_sims=400,
    )
    return [StrategyResult(**r) for r in results]


@app.get("/scenario/defaults")
def scenario_defaults():
    """Real-data-derived default dials for every team/driver - the same source
    of truth the 2026 input panel uses."""
    state = get_state()
    sc = state.scenario
    return {
        "teams": {name: vars(dials) for name, dials in sc.teams.items()},
        "drivers": {name: vars(dials) for name, dials in sc.drivers.items()},
        "driver_team": sc.driver_team,
    }


@app.post("/scenario/predict/{season}/{round_no}")
def scenario_predict(season: int, round_no: int, override: ScenarioOverride):
    state = get_state()
    # Work on a per-request COPY: the shared, data-derived defaults in
    # state.scenario must never be mutated by one caller's override, or every
    # later caller (and GET /scenario/defaults) would see the leaked value.
    sc = state.scenario.copy()
    if override.team and override.team_dials:
        sc.set_team(override.team, **override.team_dials)
    if override.driver and override.driver_dials:
        sc.set_driver(override.driver, **override.driver_dials)

    race_feats = state.feats[
        (state.feats[S.SEASON] == season) & (state.feats[S.ROUND] == round_no)
    ].copy()
    if race_feats.empty:
        raise HTTPException(404, f"No race found for season={season} round={round_no}")

    adjusted = sc.apply_to_features(race_feats)
    order = state.pipeline.race.predict_order(adjusted)
    return [
        {"driver": r[S.DRIVER], "team": r.get(S.TEAM),
         "predicted_position": int(r["predicted_position"])}
        for _, r in order.sort_values("predicted_position").iterrows()
    ]


@app.post("/predict/manual-grid")
def predict_manual_grid(grid: list[dict]):
    """Predict a finishing order from a HAND-ENTERED grid: [{"driver":"VER",
    "team":"Red Bull Racing"}, ...] in starting-grid order (P1 first). Known
    drivers/teams use their real-data-derived defaults (team names are matched
    case-insensitively). An unknown driver or a brand-new/renamed team has no
    history, so it is seeded from the real 2019-2025 debut prior, NOT a neutral
    mid-grid, and is labelled accordingly. This is for hypothetical/manual
    lineups, not historical races - there is no real season/round/circuit behind
    it.
    """
    state = get_state()
    if not grid:
        raise HTTPException(400, "Grid must contain at least one entry.")
    feat_rows = state.scenario.features_from_grid(grid)
    order = state.pipeline.race.predict_order(feat_rows).sort_values("predicted_position")

    prior = state.scenario.debut_prior
    span = (f"{prior.get('season_min')}-{prior.get('season_max')}"
            if prior.get('season_min') else "historical")
    prior_label = (
        f"no history: debut prior from real data "
        f"(expected finish P{prior.get('expected_finish', float('nan')):.1f}, "
        f"n={prior.get('n_debuts', 0)} debuts, {span})"
    )

    def _entry(r):
        e = {"predicted_position": int(r["predicted_position"]),
             "driver": r[S.DRIVER], "team": r.get(S.TEAM)}
        if bool(r.get("no_history", False)):
            e["prior"] = prior_label
        return e

    return {
        "your_grid": [
            {"position": int(r[S.F_GRID]), "driver": r[S.DRIVER], "team": r.get(S.TEAM),
             "no_history": bool(r.get("no_history", False))}
            for _, r in feat_rows.iterrows()
        ],
        "predicted_finish": [_entry(r) for _, r in order.iterrows()],
        "debut_prior": prior,
    }
