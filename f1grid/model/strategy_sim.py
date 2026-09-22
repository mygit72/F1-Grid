"""Clean-air lap-by-lap strategy simulator.

What it models (honestly):
  - per-driver clean-air base pace (from the race model / pace estimate),
  - fuel burn (cars get faster as they lighten),
  - tyre degradation + cliff per compound (model.tyres),
  - pit stops, inserted when a compound is exhausted or when the chosen sequence
    dictates a change; number of stops EMERGES from the compound sequence,
  - stochastic safety cars (Monte Carlo): random SC periods that cheapen a pit
    stop and bunch the field, run over many iterations.

What it deliberately does NOT model (stated plainly):
  - wheel-to-wheel traffic / dirty air / overtaking difficulty,
  - undercut/overcut interactions between specific cars,
  - weather changes mid-race (rain is handled as a scenario input, not dynamic).

So it answers: "in clean air, which compound sequence gives the lowest total race
time, and how does a safety car change that?" — a bounded, defensible question.
It does NOT claim "they would have finished P4."
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from f1grid.model.tyres import (
    DEFAULT_COMPOUNDS, PIT_LOSS_SECONDS, FUEL_EFFECT_PER_LAP, Compound,
)


@dataclass
class StintPlan:
    compound: str
    laps: int  # planned laps on this compound (sim may force earlier change)


def _compound(name: str, compounds) -> Compound:
    if name not in compounds:
        raise ValueError(f"Unknown compound {name!r}. Have {list(compounds)}")
    return compounds[name]


def simulate_strategy(
    base_lap_time: float,
    total_laps: int,
    sequence: list[StintPlan],
    compounds: dict | None = None,
    pit_loss: float = PIT_LOSS_SECONDS,
    rain_prob: float = 0.0,
    safety_car: bool = False,
    sc_pit_discount: float = 0.55,
    rng: np.random.Generator | None = None,
) -> dict:
    """Total race time for one driver running a given compound sequence.

    sequence: ordered StintPlans. Their laps should sum to ~total_laps; if they
    fall short the final compound is extended; if a stint exceeds a compound's
    sensible life the degradation/cliff naturally penalizes it (the sim doesn't
    forbid it — bad strategies just go slow, which is the point).
    rain_prob in [0,1]: blends in wet-compound-style pace penalty + variance.
    """
    compounds = compounds or DEFAULT_COMPOUNDS
    rng = rng or np.random.default_rng(0)

    # Normalize the plan to exactly total_laps.
    planned = sum(s.laps for s in sequence)
    seq = [StintPlan(s.compound, s.laps) for s in sequence]
    if planned < total_laps and seq:
        seq[-1].laps += (total_laps - planned)
    elif planned > total_laps:
        # trim from the end
        overflow = planned - total_laps
        for s in reversed(seq):
            take = min(s.laps - 1, overflow)
            s.laps -= take
            overflow -= take
            if overflow <= 0:
                break

    n_stops = len(seq) - 1
    total_time = 0.0
    lap = 0
    rain_var = 0.6 * rain_prob            # rain adds lap-time variance regardless of compound

    for si, stint in enumerate(seq):
        comp = _compound(stint.compound, compounds)
        rain_pen = comp.rain_penalty(rain_prob)  # compound-specific: slicks in the wet are punished hard
        for age in range(1, stint.laps + 1):
            lap += 1
            if lap > total_laps:
                break
            fuel_gain = FUEL_EFFECT_PER_LAP * (total_laps - lap)  # heavier early
            lt = (base_lap_time
                  + comp.base_offset
                  + comp.deg_at(age)
                  + fuel_gain
                  + rain_pen)
            lt += rng.normal(0, 0.15 + rain_var)  # small lap-to-lap noise
            total_time += max(lt, base_lap_time * 0.6)

        if si < len(seq) - 1:  # a pit stop follows this stint
            cost = pit_loss * (sc_pit_discount if safety_car else 1.0)
            total_time += cost

    return {
        "total_time": float(total_time),
        "n_stops": n_stops,
        "sequence": [s.compound for s in seq],
        "stint_laps": [s.laps for s in seq],
        "safety_car": safety_car,
        "rain_prob": rain_prob,
    }


def compare_strategies(
    base_lap_time: float,
    total_laps: int,
    candidate_sequences: dict[str, list[StintPlan]],
    rain_prob: float = 0.0,
    n_sims: int = 400,
    sc_lambda: float = 0.6,
    seed: int = 42,
    compounds: dict | None = None,
) -> list[dict]:
    """Monte-Carlo each candidate sequence over random safety-car occurrence.

    sc_lambda: expected number of safety-car periods per race (Poisson). Each sim
    draws whether an SC occurs; SC laps make pitting cheaper. We average total time
    across sims so the ranking reflects strategy robustness, not one lucky run.
    Returns sequences sorted by mean total time (fastest first).
    """
    rng = np.random.default_rng(seed)
    results = []
    for label, seq in candidate_sequences.items():
        times = []
        stops = None
        for _ in range(n_sims):
            sc = rng.poisson(sc_lambda) > 0
            r = simulate_strategy(
                base_lap_time, total_laps, seq, compounds=compounds,
                rain_prob=rain_prob, safety_car=sc, rng=rng,
            )
            times.append(r["total_time"])
            stops = r["n_stops"]
        times = np.array(times)
        results.append({
            "label": label,
            "sequence": [s.compound for s in seq],
            "n_stops": stops,
            "mean_time": float(times.mean()),
            "p10_time": float(np.percentile(times, 10)),
            "p90_time": float(np.percentile(times, 90)),
        })
    results.sort(key=lambda d: d["mean_time"])
    # express gap to fastest
    best = results[0]["mean_time"]
    for r in results:
        r["gap_to_best"] = round(r["mean_time"] - best, 2)
    return results
