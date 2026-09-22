"""TEST-ONLY synthetic race results.

This exists solely so the pipeline (features, training, eval) can be exercised
in an offline environment with no FastF1 access. It is NEVER imported by the real
training path and is clearly namespaced. Real runs use data.ingest.load_results().

Crucially, the synthetic generator builds finishing positions from a LATENT
driver/car strength that the feature pipeline does NOT get to see directly — the
model only ever sees lagged, observable history. This avoids the circular-label
trap of the original project (where the label was a noisy copy of an input).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from f1grid import schema as S

_TEAMS = [
    ("RBR", 0.92), ("FER", 0.88), ("MCL", 0.90), ("MER", 0.85),
    ("AST", 0.74), ("ALP", 0.70), ("WIL", 0.66), ("HAA", 0.63),
    ("SAU", 0.60), ("RB", 0.72),
]
# two drivers per team
_DRIVERS = []
for ti, (team, base) in enumerate(_TEAMS):
    for j in range(2):
        skill = base + np.random.default_rng(100 + ti * 2 + j).normal(0, 0.04)
        _DRIVERS.append((f"D{ti*2+j:02d}", team, float(np.clip(skill, 0.4, 0.99))))


def make_synthetic(seasons=(2019, 2020, 2021, 2022, 2023, 2024, 2025),
                   rounds_per_season=22, seed=42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    circuits = [f"Circuit_{i:02d}" for i in range(rounds_per_season)]
    rows = []
    # latent strengths drift slowly year to year
    strengths = {code: s for code, team, s in _DRIVERS}

    for season in seasons:
        # season-to-season drift
        for code in strengths:
            strengths[code] = float(np.clip(strengths[code] + rng.normal(0, 0.03), 0.4, 0.99))
        for rnd in range(1, rounds_per_season + 1):
            circuit = circuits[rnd - 1]
            # latent race pace = strength + race noise
            perf = []
            for code, team, _ in _DRIVERS:
                s = strengths[code]
                pace = s + rng.normal(0, 0.08)  # race-day variance
                perf.append((code, team, pace))
            # grid: qualifying is strength + its own noise (correlated w/ race)
            grid_order = sorted(
                perf, key=lambda x: -(x[2] + rng.normal(0, 0.05))
            )
            grid_map = {code: i + 1 for i, (code, _, _) in enumerate(grid_order)}
            # finishing: race pace, with DNF chance inversely related to strength
            finish_order = sorted(perf, key=lambda x: -x[2])
            for fin, (code, team, _) in enumerate(finish_order, start=1):
                dnf = 1 if rng.random() < 0.06 else 0
                finish = 21 if dnf else fin
                rows.append({
                    S.SEASON: season, S.ROUND: rnd, S.EVENT: circuit,
                    S.DATE: pd.Timestamp(f"{season}-01-01") + pd.Timedelta(days=14 * rnd),
                    S.DRIVER: code, S.DRIVER_NAME: code, S.TEAM: team,
                    S.GRID: grid_map[code], S.FINISH: finish,
                    S.STATUS: "Finished" if not dnf else "Accident", S.DNF: dnf,
                })
    return pd.DataFrame(rows).sort_values([S.SEASON, S.ROUND, S.FINISH]).reset_index(drop=True)
