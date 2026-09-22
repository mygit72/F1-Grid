"""Circuit strategy-disruption meter (item 2).

A race-level descriptor of how much tyre strategy tends to disrupt the finishing
order at a circuit, built ONLY from real pre-race information: results and lap
data from PRIOR races at the same circuit. It is shown alongside a prediction,
never fed into the model, and it never touches the fitted degradation curves
(which are known to be unreliable).

Three signals, each from prior races at the circuit (strictly before the race
being described):

  * pit_stop_spread   - how much the number of pit stops varied between drivers
                        (mean across prior races of the stdev of per-driver pit
                        counts). Needs lap data; None where laps are absent.
  * grid_finish_divergence - how much the finishing order diverged from the grid
                        (mean across prior races of mean |grid - finish|). Uses
                        results only, so it is always available.
  * sc_frequency      - fraction of prior races that had a safety car (track
                        status 4). Needs lap data; None where laps are absent.

Each available signal is normalised to 0..1 by a FIXED, domain-chosen scale (not
fit to any data, so nothing is tuned on held-out seasons). The meter score is the
mean of the available normalised signals. A circuit with no prior races at all
returns a "no history" state, never a guessed value.

Bucket thresholds (Low/Medium/High) are DESIGNED separately on 2023-2024 and
frozen (see design_thresholds / artifacts/eval/strategy_meter.json); this module
only applies them.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from f1grid.config import EVAL_DIR
from f1grid import schema as S

# Fixed normalisation scales (domain-chosen, NOT fit to data). A signal at or
# above its scale maps to 1.0.
PIT_SPREAD_SCALE = 1.0     # a 1.0-stop stdev between drivers is a lot of variety
DIVERGENCE_SCALE = 6.0     # a mean 6-position grid-to-finish move is a lot
# sc_frequency is already 0..1.

METER_ARTIFACT = EVAL_DIR / "strategy_meter.json"

# The safety-car track-status code in FastF1 lap data.
_SC_CODE = "4"


def _race_key(row) -> tuple[int, int]:
    return int(row[S.SEASON]), int(row[S.ROUND])


def pit_stop_spread_for_race(laps: pd.DataFrame, season: int, round_no: int) -> float | None:
    """Stdev across drivers of each driver's pit-stop count, for one race."""
    if laps is None or laps.empty:
        return None
    r = laps[(laps[S.SEASON] == season) & (laps[S.ROUND] == round_no)]
    if r.empty:
        return None
    pits = r.groupby(S.DRIVER)["is_pit_in"].sum()
    if len(pits) < 2:
        return None
    return float(np.std(pits.to_numpy(), ddof=0))


def safety_car_for_race(laps: pd.DataFrame, season: int, round_no: int) -> bool | None:
    """True if the race had a safety car (track status contains 4)."""
    if laps is None or laps.empty:
        return None
    r = laps[(laps[S.SEASON] == season) & (laps[S.ROUND] == round_no)]
    if r.empty:
        return None
    return bool(r["track_status"].astype(str).str.contains(_SC_CODE).any())


def grid_finish_divergence_for_race(results: pd.DataFrame, season: int,
                                    round_no: int) -> float | None:
    """Mean |grid - finish| across classified drivers, for one race."""
    r = results[(results[S.SEASON] == season) & (results[S.ROUND] == round_no)]
    r = r[(r[S.GRID] > 0) & (r[S.FINISH] > 0)]
    if len(r) < 5:
        return None
    return float(np.mean(np.abs(r[S.GRID].to_numpy() - r[S.FINISH].to_numpy())))


def prior_circuit_races(results: pd.DataFrame, event_name: str,
                        season: int, round_no: int) -> pd.DataFrame:
    """Distinct (season, round) races at this circuit STRICTLY before (season,
    round). 'Before' means an earlier season, or the same season and an earlier
    round."""
    same = results[results[S.EVENT] == event_name]
    before = same[(same[S.SEASON] < season) |
                  ((same[S.SEASON] == season) & (same[S.ROUND] < round_no))]
    return before[[S.SEASON, S.ROUND]].drop_duplicates().sort_values([S.SEASON, S.ROUND])


def raw_signals(results: pd.DataFrame, laps: pd.DataFrame, event_name: str,
                season: int, round_no: int) -> dict:
    """Aggregate the three signals over prior races at the circuit.

    Returns raw (un-normalised) means plus the count of prior races each signal
    was available from. Signals with no data are None.
    """
    prior = prior_circuit_races(results, event_name, season, round_no)
    n_prior = len(prior)

    div, pit, sc = [], [], []
    for _, pr in prior.iterrows():
        s, rr = int(pr[S.SEASON]), int(pr[S.ROUND])
        d = grid_finish_divergence_for_race(results, s, rr)
        if d is not None:
            div.append(d)
        p = pit_stop_spread_for_race(laps, s, rr)
        if p is not None:
            pit.append(p)
        c = safety_car_for_race(laps, s, rr)
        if c is not None:
            sc.append(1.0 if c else 0.0)

    return {
        "n_prior_races": int(n_prior),
        "grid_finish_divergence": float(np.mean(div)) if div else None,
        "pit_stop_spread": float(np.mean(pit)) if pit else None,
        "sc_frequency": float(np.mean(sc)) if sc else None,
        "n_races_with_laps": int(len(pit)),
    }


def _normalise(sig: dict) -> dict:
    out = {}
    if sig["grid_finish_divergence"] is not None:
        out["divergence_norm"] = min(sig["grid_finish_divergence"] / DIVERGENCE_SCALE, 1.0)
    if sig["pit_stop_spread"] is not None:
        out["pit_spread_norm"] = min(sig["pit_stop_spread"] / PIT_SPREAD_SCALE, 1.0)
    if sig["sc_frequency"] is not None:
        out["sc_norm"] = float(sig["sc_frequency"])
    return out


def meter_score(results: pd.DataFrame, laps: pd.DataFrame, event_name: str,
                season: int, round_no: int) -> dict:
    """Compute the raw meter score (0..1) for a race, or a no-history state.

    No bucket/label is assigned here; that requires the frozen thresholds and is
    done by `classify`. This function is leakage-free by construction: it reads
    only races strictly before (season, round).
    """
    sig = raw_signals(results, laps, event_name, season, round_no)
    norms = _normalise(sig)
    if sig["n_prior_races"] == 0 or not norms:
        return {
            "has_history": False,
            "score": None,
            "signals": sig,
            "normalised": norms,
            "components_used": sorted(norms.keys()),
        }
    score = float(np.mean(list(norms.values())))
    return {
        "has_history": True,
        "score": score,
        "signals": sig,
        "normalised": norms,
        "components_used": sorted(norms.keys()),
    }


def assert_no_leakage(results: pd.DataFrame, laps: pd.DataFrame,
                      event_name: str, season: int, round_no: int) -> None:
    """Independent leakage check for the meter's new inputs.

    The meter for race R must depend only on races strictly before R. Corrupt
    race R's OWN result (reverse its finish and grid) and confirm the meter score
    is byte-for-byte unchanged. If any signal peeked at R's own outcome, reversing
    it would move the score.
    """
    before = meter_score(results, laps, event_name, season, round_no)
    corrupt = results.copy()
    mask = (corrupt[S.SEASON] == season) & (corrupt[S.ROUND] == round_no)
    if mask.any():
        for col in (S.FINISH, S.GRID):
            vals = corrupt.loc[mask, col]
            corrupt.loc[mask, col] = vals.max() - vals + 1
    after = meter_score(corrupt, laps, event_name, season, round_no)
    if before["score"] != after["score"] or before["signals"] != after["signals"]:
        raise AssertionError(
            f"Strategy meter leaked: score for {season} R{round_no} {event_name} "
            f"changed when its OWN result was corrupted "
            f"({before['score']} -> {after['score']}).")


def design_thresholds(scores: list[float]) -> dict:
    """Tertile thresholds from a DESIGN-period list of meter scores (2023-2024).

    Frozen and stored; never recomputed on held-out data.
    """
    arr = np.asarray([s for s in scores if s is not None], dtype=float)
    t1 = float(np.quantile(arr, 1 / 3))
    t2 = float(np.quantile(arr, 2 / 3))
    return {"t1": t1, "t2": t2, "n_design_races": int(len(arr))}


def load_thresholds(path: Path = METER_ARTIFACT) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def bucket_for(score: float, thresholds: dict) -> str:
    if score < thresholds["t1"]:
        return "Low"
    if score < thresholds["t2"]:
        return "Medium"
    return "High"


def _one_line_reason(m: dict) -> str:
    sig = m["signals"]
    parts = []
    if sig.get("grid_finish_divergence") is not None:
        parts.append(f"grid-to-finish moves average "
                     f"{sig['grid_finish_divergence']:.1f} places")
    if sig.get("pit_stop_spread") is not None:
        parts.append(f"pit-stop counts vary by "
                     f"{sig['pit_stop_spread']:.2f} (stdev)")
    if sig.get("sc_frequency") is not None:
        parts.append(f"safety cars in {sig['sc_frequency'] * 100:.0f}% of prior races")
    scope = f"{sig['n_prior_races']} prior race(s) at this circuit"
    if not parts:
        return scope
    return "; ".join(parts) + f" (from {scope})"


def classify_from_artifact(results: pd.DataFrame, laps: pd.DataFrame,
                           event_name: str, season: int, round_no: int,
                           artifact: Path = METER_ARTIFACT) -> dict:
    """Classify using the frozen thresholds AND the validated label_mode from the
    validation artifact. If the artifact is missing, falls back to the safe
    "complexity" wording with no thresholds (score only, no level)."""
    cfg = load_thresholds(artifact)
    if cfg and "t1" in cfg:
        thresholds = {"t1": cfg["t1"], "t2": cfg["t2"]}
        label_mode = cfg.get("label_mode", "complexity")
    else:
        thresholds, label_mode = None, "complexity"
    return classify(results, laps, event_name, season, round_no,
                    thresholds=thresholds, label_mode=label_mode)


def classify(results: pd.DataFrame, laps: pd.DataFrame, event_name: str,
             season: int, round_no: int, thresholds: dict | None = None,
             label_mode: str = "complexity") -> dict:
    """Full meter payload for a race: score, bucket (or no-history), reason.

    `label_mode` selects the vocabulary decided by validation:
      * "confidence" -> field label "Prediction confidence (strategy-based)"
        with Low/Medium/High meaning the meter earned a confidence claim.
      * "complexity" (default, the safe outcome) -> "Strategy complexity" with
        the SAME Low/Medium/High description but NO confidence claim.
    The numeric score and buckets are identical; only the wording differs.
    """
    thresholds = thresholds or load_thresholds()
    m = meter_score(results, laps, event_name, season, round_no)
    label = ("Prediction confidence (strategy-based)"
             if label_mode == "confidence" else "Strategy complexity")
    is_confidence = label_mode == "confidence"

    if not m["has_history"]:
        return {
            "label": label,
            "is_confidence": is_confidence,
            "state": "no_history",
            "level": None,
            "score": None,
            "reason": "No prior races at this circuit, so strategy disruption "
                      "cannot be estimated.",
            "signals": m["signals"],
            "components_used": m["components_used"],
        }
    if thresholds is None:
        # Cannot bucket without frozen thresholds; expose the score, no level.
        level = None
    else:
        level = bucket_for(m["score"], thresholds)
    return {
        "label": label,
        "is_confidence": is_confidence,
        "state": "ok",
        "level": level,
        "score": round(m["score"], 4),
        "reason": _one_line_reason(m),
        "signals": m["signals"],
        "components_used": m["components_used"],
    }
