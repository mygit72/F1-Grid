"""Tyre compound model.

Each compound has:
  - base_offset: pace delta vs a reference compound when fresh (soft fastest).
  - deg_rate: linear time loss per lap of wear (s/lap).
  - cliff_lap: stint age where degradation accelerates sharply ("the cliff").
  - cliff_rate: extra s/lap once past the cliff.

These defaults are reasonable real-world starting values; `fit_from_stints()`
shows how to replace them with values learned from real FastF1 stint lap times
(fuel-corrected). Until you run that locally, the defaults are explicit, named
assumptions — not hidden in a model.

A stint's lap time contribution from tyres at stint-age a:
    deg(a) = deg_rate * a + max(0, a - cliff_lap) * cliff_rate
The compound's usable life is where deg(a) gets large enough that pitting for a
fresh tyre is faster than continuing — the simulator computes this rather than
us declaring "softs last 15 laps".
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Compound:
    name: str
    base_offset: float   # s/lap vs reference when fresh (negative = faster)
    deg_rate: float       # s/lap linear degradation
    cliff_lap: int        # stint age where the cliff starts
    cliff_rate: float     # extra s/lap past the cliff
    rain_suitability: float = 0.0  # 0 = built for dry, 1 = built for full wet

    def deg_at(self, stint_age: int) -> float:
        extra = max(0, stint_age - self.cliff_lap) * self.cliff_rate
        return self.deg_rate * stint_age + extra

    def rain_penalty(self, rain_prob: float) -> float:
        """Pace lost to wet conditions, given how unsuited this compound is.

        A slick (rain_suitability=0) run in full wet (rain_prob=1) loses a huge
        amount of time — aquaplaning and zero grip, not a flat handicap. A wet
        tyre in the same conditions loses almost nothing. The mismatch is what
        costs time, not rain itself, which is why strategy choice actually
        matters here.
        """
        mismatch = abs(rain_prob - self.rain_suitability)
        # Quadratic growth: a slick in heavy rain (mismatch~1) costs far more
        # than a slightly-wrong choice (mismatch~0.3). Capped at a severe but
        # finite penalty so the simulator never produces an actual infinity.
        return 35.0 * (mismatch ** 2)


# Default 2026-plausible compound set (relative pace; tune via fit_from_stints).
DEFAULT_COMPOUNDS = {
    "SOFT":   Compound("SOFT",   base_offset=-0.6, deg_rate=0.09,  cliff_lap=12, cliff_rate=0.25, rain_suitability=0.0),
    "MEDIUM": Compound("MEDIUM", base_offset=-0.2, deg_rate=0.055, cliff_lap=22, cliff_rate=0.18, rain_suitability=0.0),
    "HARD":   Compound("HARD",   base_offset=0.0,  deg_rate=0.035, cliff_lap=34, cliff_rate=0.12, rain_suitability=0.0),
    "INTER":  Compound("INTER",  base_offset=2.5,  deg_rate=0.05,  cliff_lap=25, cliff_rate=0.15, rain_suitability=0.5),
    "WET":    Compound("WET",    base_offset=5.0,  deg_rate=0.04,  cliff_lap=30, cliff_rate=0.12, rain_suitability=1.0),
}

PIT_LOSS_SECONDS = 22.0       # pit lane transit + stationary (circuit-tunable)
FUEL_EFFECT_PER_LAP = 0.045   # car lightens -> faster each lap (s/lap improvement)


def fit_from_stints(laps, before=None, circuit=None):
    """Learn deg_rate/base_offset per compound from real FastF1 lap data.

    `laps`: a lap-level DataFrame as produced by `f1grid.data.laps` (columns incl.
    season, round, event_name, event_date, driver, lap_number, lap_time_s, stint,
    compound, tyre_life, is_pit_in, is_pit_out, track_status). The fitting removes
    the fuel effect by ESTIMATING it (see `model.tyre_fit`), fits degradation per
    compound (pooled, with an optional per-circuit curve), and keeps the documented
    default cliff (labelled) because the cliff is usually censored - teams pit
    before it. Wet/intermediate keep labelled defaults unless there is enough wet
    running.

    `before=(season, round)` restricts fitting to races strictly before that race
    so a curve used to simulate/evaluate a race is never fitted on it (leakage).
    Returns a dict[str, Compound]; the full fit summary (counts, fuel estimate,
    cliff observed-rate) is available via `model.tyre_fit.fit_curves`.
    """
    from f1grid.model.tyre_fit import fit_curves  # local import avoids a cycle
    return fit_curves(laps, before=before).compounds(circuit=circuit)
