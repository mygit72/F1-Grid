"""Pre-race publishing workflow.

    python -m f1grid.publish --next            # publish the next upcoming race
    python -m f1grid.publish --next --rain-prob 0.4
    python -m f1grid.publish --score           # grade any published races that have run

`--next` finds the next upcoming race from the authoritative schedule, builds
features for it from ONLY the data available now (every completed race in the
parquet), trains the two-stage pipeline on that data, predicts the order, and
writes the prediction through the store's pre-race boundary. Because the store
timestamps with its own clock and checks the authoritative race start, the
published record is a genuine, verifiable pre-race prediction.

`--score` grades every PUBLIC prediction whose race now has a real result,
appending to the public scorecard. It never touches the backtest archive.

No network is required here: it reads the cached results parquet and schedule
artifact that `data.ingest` produced. Run `data.ingest` first to refresh them.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone

import pandas as pd

from f1grid import schema as S
from f1grid.config import CONFIG
from f1grid.data.ingest import load_results
from f1grid.features.build import build_features
from f1grid.model.pipeline import TwoStagePipeline
from f1grid.model.montecarlo import monte_carlo_outcomes
from f1grid.store import schedule as sched
from f1grid.store.predictions import save_prediction, RetroactivePredictionError, load_predictions
from f1grid.score.scorer import score_race, track_record


def _latest_completed_key(results: pd.DataFrame) -> tuple[int, int]:
    ordered = results.sort_values([S.SEASON, S.ROUND])
    last = ordered[[S.SEASON, S.ROUND]].iloc[-1]
    return int(last[S.SEASON]), int(last[S.ROUND])


def build_upcoming_features(results: pd.DataFrame, upcoming: dict):
    """Return (upcoming_feats, train_feats) for a race not yet in the results.

    The expected lineup is taken from the most recent completed race (the best
    proxy for the next grid). Placeholder grid/finish are inserted only so the
    leakage-free builder can compute each driver's as-of features (form, points-
    to-date, circuit history, experience); the placeholders are never read as
    features and the placeholder rows are excluded from training.
    """
    l_season, l_round = _latest_completed_key(results)
    lineup = results[(results[S.SEASON] == l_season) & (results[S.ROUND] == l_round)][
        [S.DRIVER, S.DRIVER_NAME, S.TEAM]
    ].drop_duplicates()

    # Match the parquet's tz-naive DATE column (avoid mixing tz-aware/naive).
    start = pd.Timestamp(upcoming["race_start_utc"]).tz_localize(None)
    placeholder = [{
        S.SEASON: upcoming["season"], S.ROUND: upcoming["round"],
        S.EVENT: upcoming["event"], S.DATE: start,
        S.DRIVER: r[S.DRIVER], S.DRIVER_NAME: r[S.DRIVER_NAME], S.TEAM: r[S.TEAM],
        S.GRID: 1, S.FINISH: 1, S.STATUS: "Scheduled", S.DNF: 0,
    } for _, r in lineup.iterrows()]

    aug = pd.concat([results, pd.DataFrame(placeholder)], ignore_index=True)
    feats = build_features(aug)
    is_upcoming = (feats[S.SEASON] == upcoming["season"]) & (feats[S.ROUND] == upcoming["round"])
    return feats[is_upcoming].copy(), feats[~is_upcoming].copy()


def publish_next(season: int = 2026, rain_prob: float = 0.0,
                 now_utc: datetime | None = None, backtest: bool = False):
    now_utc = now_utc or datetime.now(timezone.utc)
    results = load_results()
    upcoming = sched.next_upcoming_race(season, now_utc=now_utc)
    if upcoming is None:
        print(f"No upcoming {season} race found in the schedule (season may be over).")
        return None

    print(f"Next upcoming race: {season} R{upcoming['round']} {upcoming['event']} "
          f"(starts {upcoming['race_start_utc'].isoformat()})")

    upcoming_feats, train_feats = build_upcoming_features(results, upcoming)
    if upcoming_feats.empty:
        print("Could not build features for the upcoming race.")
        return None

    print(f"Training pipeline on {train_feats['race_id'].nunique()} completed races...")
    pipe = TwoStagePipeline().fit(train_feats)
    order = pipe.predict_weekend(upcoming_feats, use_real_grid=False)
    order["wet_skill"] = order.get("wet_skill", 0.5)
    mc = monte_carlo_outcomes(order, rain_prob=rain_prob, n_sims=3000)
    merged = order.merge(
        mc[[S.DRIVER, "win_prob", "podium_prob", "points_prob", "dnf_prob"]], on=S.DRIVER
    ).sort_values("predicted_position")

    l_season, l_round = _latest_completed_key(results)
    try:
        path = save_prediction(
            upcoming["season"], upcoming["round"], upcoming["event"], merged,
            data_cutoff=f"as of {l_season} R{l_round}", rain_prob=rain_prob,
            backtest=backtest,
            model_meta={"backend": pipe.race.backend, "trained_races": int(train_feats['race_id'].nunique())},
            now_utc=now_utc,
        )
    except RetroactivePredictionError as e:
        print(f"REFUSED: {e}")
        return None

    tag = "BACKTEST" if backtest else "PUBLIC pre-race"
    print(f"Published ({tag}): {path.name}")
    print(merged[[S.DRIVER, S.TEAM, "predicted_position", "win_prob"]]
          .head(10).to_string(index=False))
    return path


def score_published(results: pd.DataFrame | None = None) -> list[tuple[int, int]]:
    """Grade every PUBLIC prediction whose race now has a real result."""
    results = results if results is not None else load_results()
    seen, scored = set(), []
    for rec in load_predictions():
        key = (rec["season"], rec["round"])
        if key in seen:
            continue
        seen.add(key)
        actual = results[(results[S.SEASON] == key[0]) & (results[S.ROUND] == key[1])]
        if actual.empty:
            print(f"  {key[0]} R{key[1]} {rec['event']}: no result yet, skipping.")
            continue
        row = score_race(key[0], key[1], results)
        if row:
            scored.append(key)
            print(f"  Scored {key[0]} R{key[1]} {rec['event']}: "
                  f"top1={row['top1_acc']}, podium={row['podium_acc']}, "
                  f"spearman={row['spearman']} (baseline {row['baseline_spearman']})")
    if not scored:
        print("No published predictions had a result to grade.")
    return scored


def main():
    ap = argparse.ArgumentParser(description="Pre-race publish/score workflow.")
    ap.add_argument("--next", action="store_true", help="Publish the next upcoming race.")
    ap.add_argument("--score", action="store_true", help="Grade published races that have run.")
    ap.add_argument("--season", type=int, default=max(CONFIG.eval_seasons) + 1)
    ap.add_argument("--rain-prob", type=float, default=0.0)
    ap.add_argument("--backtest", action="store_true",
                    help="Store to the separate backtest archive instead of the public record.")
    args = ap.parse_args()

    if not (args.next or args.score):
        ap.error("Pass --next and/or --score.")
    if args.next:
        publish_next(season=args.season, rain_prob=args.rain_prob, backtest=args.backtest)
    if args.score:
        score_published()
        tr = track_record()
        if not tr.empty:
            print("\nPublic track record:")
            print(tr.to_string(index=False))


if __name__ == "__main__":
    main()
