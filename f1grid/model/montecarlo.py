"""Monte Carlo race-outcome layer.

Turns the race model's deterministic scores into outcome probabilities (win,
podium, points, expected position) by simulating the race many times with:
  - performance noise (race-day variance),
  - DNF draws from each driver's modeled DNF rate,
  - a RAIN SCENARIO (manual 0..1 probability) that (a) increases variance —
    rain shuffles the order — and (b) re-weights driver wet skill so wet-strong
    drivers gain. Rain is a user-set scenario input, not a weather forecast.

Wet skill: if a per-driver `wet_skill` (0..1) is provided we use it; otherwise we
fall back to neutral 0.5 so the layer still runs. On real data you can derive
wet_skill from historical wet-race overperformance (FastF1 weather flags).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from f1grid import schema as S


def monte_carlo_outcomes(
    scored: pd.DataFrame,
    rain_prob: float = 0.0,
    n_sims: int = 5000,
    base_noise: float = 1.6,
    dnf_col: str = S.F_DNF_RATE,
    wet_skill_col: str = "wet_skill",
    seed: int = 42,
) -> pd.DataFrame:
    """scored: race rows with `model_score` (higher=better) and a DNF-rate column.

    Returns per-driver probabilities sorted by win probability.
    """
    rng = np.random.default_rng(seed)
    df = scored.reset_index(drop=True).copy()
    n = len(df)

    # Convert model score to a latent "strength" (higher = better). Standardize so
    # noise has a consistent scale across races.
    s = df["model_score"].to_numpy(dtype=float)
    s = (s - s.mean()) / (s.std() + 1e-9)

    dnf_rate = (
        df[dnf_col].to_numpy(dtype=float) if dnf_col in df.columns
        else np.full(n, 0.1)
    )
    dnf_rate = np.clip(dnf_rate, 0.02, 0.4)

    wet = (
        df[wet_skill_col].to_numpy(dtype=float) if wet_skill_col in df.columns
        else np.full(n, 0.5)
    )

    # Rain widens variance and tilts strength toward wet-skilled drivers.
    noise_scale = base_noise * (1.0 + 1.2 * rain_prob)
    wet_tilt = (wet - 0.5) * 2.0 * rain_prob  # +- shift in strength units
    strength = s + wet_tilt

    pos_counts = np.zeros((n, n))
    dnf_counts = np.zeros(n)

    for _ in range(n_sims):
        draw = strength + rng.normal(0, noise_scale, n)
        dnf_mask = rng.random(n) < dnf_rate * (1.0 + 0.8 * rain_prob)
        draw[dnf_mask] -= 100.0  # DNFs sink to the back
        dnf_counts += dnf_mask
        order = np.argsort(-draw)  # best first
        for finish_idx, drv_i in enumerate(order):
            pos_counts[drv_i, finish_idx] += 1

    probs = pos_counts / n_sims
    out = df[[c for c in [S.DRIVER, S.TEAM, "predicted_position", "model_score"]
              if c in df.columns]].copy()
    out["win_prob"] = probs[:, 0]
    out["podium_prob"] = probs[:, :3].sum(axis=1)
    out["points_prob"] = probs[:, :10].sum(axis=1)
    out["expected_position"] = (probs * np.arange(1, n + 1)).sum(axis=1)
    out["dnf_prob"] = dnf_counts / n_sims
    out = out.sort_values("win_prob", ascending=False).reset_index(drop=True)
    out["rain_prob"] = rain_prob
    return out
