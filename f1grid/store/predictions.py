"""Immutable, timestamped prediction store - the credibility centerpiece.

When you predict an upcoming race, the prediction is written to a JSON file named
with the UTC timestamp and a content hash. The record captures when it was made
(UTC), the data cutoff, model versions, the full predicted order + probabilities,
and the rain scenario. Files are never overwritten, so the history is append-only.

THE HARD BOUNDARY (enforced HERE, in the store, not just the UI):
    A prediction may only enter the PUBLIC track record if it was made strictly
    BEFORE the race started. This is what makes "verified pre-race" mean anything.

Two things make the boundary un-foolable:
  1. `made_at` is always THIS process's own UTC clock - never a caller-supplied
     value - so a forged/backdated timestamp is impossible.
  2. The race start time is looked up AUTHORITATIVELY from the schedule artifact
     (store.schedule) and overrides anything a caller passes, so you cannot sneak
     a finished race in by claiming a fake future start.
A retroactive prediction is refused from the public store; an explicit backtest is
written to a SEPARATE directory (artifacts/backtests) that the scorer/track record
never read.
"""
from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from f1grid.config import PRED_DIR, BACKTEST_DIR
from f1grid import schema as S
from f1grid.store import schedule as _schedule


class RetroactivePredictionError(RuntimeError):
    """Raised when a not-pre-race prediction is refused from the public store."""


def _utc_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _slug(text: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in str(text)).strip("_")


def save_prediction(
    season: int,
    round_no: int,
    event: str,
    predicted: pd.DataFrame,
    data_cutoff: str,
    rain_prob: float = 0.0,
    model_meta: dict | None = None,
    pred_dir: Path = PRED_DIR,
    *,
    race_start_utc: datetime | None = None,
    backtest: bool = False,
    backtest_dir: Path = BACKTEST_DIR,
    now_utc: datetime | None = None,
    schedule_lookup=None,
    quali_lookup=None,
    strategy_meter: dict | None = None,
) -> Path:
    """Write a prediction record, enforcing the pre-race boundary.

    - Public path (backtest=False): the prediction is written only if made
      strictly before the race start; otherwise `RetroactivePredictionError`.
    - Backtest path (backtest=True): always written to `backtest_dir`, clearly
      marked, and never mixed with the public track record.

    `now_utc` and `schedule_lookup` are for tests only; production callers must
    leave them None so the real clock and the real schedule artifact are used.
    `race_start_utc` is only consulted when the schedule has no authoritative
    entry for this race.
    """
    made_at_dt = (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)

    # Authoritative race start ALWAYS wins over a caller-supplied value.
    lookup = schedule_lookup or _schedule.race_start_utc
    authoritative = lookup(season, round_no)
    effective_start = authoritative if authoritative is not None else race_start_utc
    if effective_start is not None and effective_start.tzinfo is None:
        effective_start = effective_start.replace(tzinfo=timezone.utc)

    if effective_start is None and not backtest:
        raise RetroactivePredictionError(
            f"No authoritative race-start time for {season} R{round_no}; refusing "
            f"to publish to the public track record. Run data.ingest to write the "
            f"schedule, or use backtest=True for an explicitly separate record."
        )

    is_pre_race = effective_start is not None and made_at_dt < effective_start

    # Pre-qualifying flag (item 2): selects the fair scoring baseline later. A
    # prediction made before the grid-setting qualifying session is compared to
    # pre-qualifying baselines; one made after, to the grid-order baseline. The
    # quali time is looked up authoritatively, like the race start.
    qlookup = quali_lookup or _schedule.quali_start_utc
    quali_start = qlookup(season, round_no)
    if quali_start is not None and quali_start.tzinfo is None:
        quali_start = quali_start.replace(tzinfo=timezone.utc)
    pre_qualifying = None
    if quali_start is not None:
        pre_qualifying = bool(made_at_dt < quali_start)

    if not backtest and not is_pre_race:
        raise RetroactivePredictionError(
            f"Race {season} R{round_no} started at "
            f"{_utc_iso(effective_start)} but this prediction was made at "
            f"{_utc_iso(made_at_dt)}. A retroactive prediction cannot enter the "
            f"public track record. Publish before the race, or pass backtest=True "
            f"to store it in the separate backtest archive."
        )

    target_dir = backtest_dir if backtest else pred_dir
    target_dir.mkdir(parents=True, exist_ok=True)

    made_at = _utc_iso(made_at_dt)
    cols = [c for c in [S.DRIVER, S.TEAM, "predicted_position", "win_prob",
                        "podium_prob", "points_prob", "expected_position"]
            if c in predicted.columns]
    order = (
        predicted.sort_values("predicted_position")[cols]
        .to_dict(orient="records")
    )

    record = {
        "made_at_utc": made_at,
        "race_start_utc": _utc_iso(effective_start) if effective_start else None,
        "quali_start_utc": _utc_iso(quali_start) if quali_start else None,
        "is_pre_race": bool(is_pre_race),
        "pre_qualifying": pre_qualifying,
        "is_backtest": bool(backtest),
        "data_cutoff": data_cutoff,          # last race the model could see
        "season": int(season),
        "round": int(round_no),
        "event": event,
        "rain_prob": float(rain_prob),
        "model_meta": model_meta or {},
        "prediction": order,
        "schema_version": 3,
    }
    # Item 2: the circuit strategy meter travels WITH the prediction as a new,
    # optional field. Older files simply lack it; the loader tolerates both.
    if strategy_meter is not None:
        record["strategy_meter"] = strategy_meter

    payload = json.dumps(record, sort_keys=True, default=str)
    h = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:10]
    record["content_hash"] = h
    nonce = secrets.token_hex(3)  # guarantees uniqueness even for identical
                                   # content saved within the same second
    record["nonce"] = nonce

    prefix = "BACKTEST_" if backtest else ""
    fname = (f"{prefix}{season}_R{round_no:02d}_{_slug(event)}__"
            f"{made_at.replace(':','')}__{h}_{nonce}.json")
    path = target_dir / fname
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite immutable record {path}")
    path.write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")
    return path


def load_predictions(season: int | None = None,
                     round_no: int | None = None,
                     pred_dir: Path = PRED_DIR) -> list[dict]:
    """Load PUBLIC prediction records (pred_dir), optionally filtered.

    The public track record only ever reads PRED_DIR; backtest records live in a
    separate directory and are never returned here.
    """
    records = []
    if not pred_dir.exists():
        return records
    for p in sorted(pred_dir.glob("*.json")):
        rec = json.loads(p.read_text(encoding="utf-8"))
        if season is not None and rec.get("season") != season:
            continue
        if round_no is not None and rec.get("round") != round_no:
            continue
        rec["_path"] = str(p)
        records.append(rec)
    return records


def latest_prediction(season: int, round_no: int,
                      pred_dir: Path = PRED_DIR) -> dict | None:
    recs = load_predictions(season, round_no, pred_dir)
    if not recs:
        return None
    return max(recs, key=lambda r: r["made_at_utc"])
