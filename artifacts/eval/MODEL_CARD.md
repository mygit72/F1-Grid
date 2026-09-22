# F1Grid Model Card
_Generated 2026-09-21 17:18 UTC on 3.12.10 / xgboost backend_

## What this is
A two-stage Formula 1 prediction system: a qualifying model predicts the starting grid from pre-qualifying signal, and a race model predicts the full finishing order. Every feature is computed from races strictly prior to the one being predicted (verified by an automated leakage check). All evaluation below is walk-forward: the model only ever sees the past when predicting a race, never random k-fold splits.

## Data
- Seasons cached: [2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]
- Trained on: [2019, 2020, 2021, 2022, 2023, 2024] (2,559 driver-race rows)
- Evaluated (held out) on: [2025]
- Races per season (ground truth from the parquet): {2019: 21, 2020: 17, 2021: 22, 2022: 22, 2023: 22, 2024: 24, 2025: 24, 2026: 14}

## Team identity across seasons (2026: Audi, Cadillac)
Every team feature the model uses (e.g. team points-to-date) is SEASON-TO-DATE and resets each season by construction - there is no cross-season team-strength feature. Consequences, applied uniformly to every team:
- A constructor rename (Kick Sauber -> Audi, and historically Renault -> Alpine, Racing Point -> Aston Martin, Toro Rosso -> AlphaTauri -> RB -> Racing Bulls) carries NO team history across the rename, because no team carries team history across a season boundary. The renamed team accumulates its within-season points under the new name exactly as any team does. So the rename is a no-op for the features, and we do not fabricate a carried-forward strength.
- A brand-new team (Cadillac) is identical at the team level: it starts each season at zero season-to-date points.
- The distinction that actually matters is at the DRIVER level: a returning driver keeps their own form/experience features across any team change, while a genuine debutant (or an unknown entry in the manual-grid tool) is seeded from the real historical debut prior (how first-race drivers across the cached seasons actually finished), never a neutral mid-grid.

## Race model alone (given the real grid) vs. grid-order baseline

| system | races | spearman | top1 acc | podium acc | mae (positions) |
|---|---|---|---|---|---|
| F1Grid model | 24 | 0.617 | 0.500 | 0.681 | 3.87 |
| Grid-order baseline | 24 | 0.652 | 0.667 | 0.750 | 3.62 |

**Beats grid-order baseline on held-out data: NOT YET** (spearman 0.617 vs 0.652).

## End-to-end (qualifying error included)
Same metrics, but using the QUALI MODEL's predicted grid instead of the real grid - this is what a prediction published before qualifying actually looks like, including compounded error from stage 1.

| scenario | spearman | top1 acc | podium acc | mae (positions) |
|---|---|---|---|---|
| Race model, real grid given | 0.617 | 0.500 | 0.681 | 3.87 |
| Full pipeline, predicted grid | 0.522 | 0.208 | 0.542 | 4.51 |

## End-to-end pipeline vs. pre-qualifying baselines (held-out [2025])
What a prediction published BEFORE qualifying can be judged against fairly: the full pipeline (predicted grid) vs two baselines available at that same moment. Championship-standings = season-to-date points order; Previous-race = the prior race's finishing order (season openers fall back to the previous season's finale; drivers who did not start the prior race are ranked behind those who did, by their most recent prior finish, with true debutants last). Both use only races before this one and are covered by the leakage self-check.

| system | races | spearman | top1 acc | podium acc | mae (positions) |
|---|---|---|---|---|---|
| Full pipeline (predicted grid) | 24 | 0.522 | 0.208 | 0.542 | 4.51 |
| Championship-standings baseline | 24 | 0.528 | 0.208 | 0.653 | 4.48 |
| Previous-race baseline | 24 | 0.433 | 0.333 | 0.556 | 4.83 |

**Beats pre-qualifying baselines: NOT YET** (pipeline spearman 0.522 vs strongest baseline Championship-standings baseline 0.528).

## End-to-end pipeline vs. pre-qualifying baselines (completed [2026] (walk-forward))
What a prediction published BEFORE qualifying can be judged against fairly: the full pipeline (predicted grid) vs two baselines available at that same moment. Championship-standings = season-to-date points order; Previous-race = the prior race's finishing order (season openers fall back to the previous season's finale; drivers who did not start the prior race are ranked behind those who did, by their most recent prior finish, with true debutants last). Both use only races before this one and are covered by the leakage self-check.

| system | races | spearman | top1 acc | podium acc | mae (positions) |
|---|---|---|---|---|---|
| Full pipeline (predicted grid) | 14 | 0.613 | 0.214 | 0.548 | 4.03 |
| Championship-standings baseline | 14 | 0.569 | 0.500 | 0.476 | 4.33 |
| Previous-race baseline | 14 | 0.418 | 0.429 | 0.476 | 5.06 |

**Beats pre-qualifying baselines: YES** (pipeline spearman 0.613 vs strongest baseline Championship-standings baseline 0.569).

## Strategy-feature ablation (item 4)
Circuit-level features (pit loss, typical stops, overtaking difficulty, fitted degradation level), each computed only from races before the one predicted and covered by the leakage self-check. Feature set chosen on walk-forward validation over [2023, 2024] ONLY; held-out numbers below are reported once and were not used to choose.

| set | spearman | top1 acc | podium acc | mae |
|---|---|---|---|---|
| validation [2023, 2024] - base | 0.639 | 0.500 | 0.558 | 3.85 |
| validation [2023, 2024] - +strategy | 0.666 | 0.543 | 0.609 | 3.65 |
| held-out 2025 - base | 0.617 | 0.500 | 0.681 | 3.87 |
| held-out 2025 - +strategy | 0.610 | 0.333 | 0.708 | 3.97 |
| [2026] walk-forward - base | 0.637 | 0.429 | 0.643 | 3.84 |
| [2026] walk-forward - +strategy | 0.615 | 0.429 | 0.548 | 3.99 |

**Validation decision:** strategy features helped on [2023, 2024]. **Held-out:** the gain did NOT generalize (2025 and 2026 both reported above).
**In production: NO.** They are LEFT OUT: a validation gain that does not generalize to held-out data is not shipped. A null/negative result is a valid, reported outcome; production keeps the base feature set.

## Tyre-degradation fit (items 3 and 6): refit on 2022+ era

Refitted from real FastF1 stint laps over the 2022+ regulation era (57 events;
50,523 of 60,630 dry laps kept after filtering safety-car/VSC/yellow, pit in/out,
lap 1, and large-gap outlier laps). Lap coverage is 2022-2024 (2024 partial,
rounds 1-15); 2025-2026 laps are pending a FastF1 500-calls/hour rate-limit reset.
Fuel effect was ESTIMATED from the data: 0.06709 s/lap.

| compound | deg (s/lap) | base offset | stints | laps | max life seen | cliff (age) | reach rate | cliff observed |
|---|---|---|---|---|---|---|---|---|
| SOFT | 0.07201 | -0.0202 | 525 | 6863 | 49.0 | 12 (default) | 0.7486 | True |
| MEDIUM | 0.07271 | -0.2872 | 1170 | 19044 | 77.0 | 22 (default) | 0.3151 | False |
| HARD | 0.05004 | 0.0 | 1047 | 24284 | 78.0 | 34 (default) | 0.2510 | False |

Compound ordering: HARD is now correctly the slowest-degrading, but SOFT and
MEDIUM are inseparable (0.07201 vs 0.07271, MEDIUM marginally faster) and SOFT's
fitted fresh pace (-0.0202) is slower than MEDIUM's (-0.2872), which is physically
backwards. So the ordering is still NOT correct (soft is not fastest-degrading).
This is the same identification limit as before: within a stint tyre-life and
lap-number are collinear, and each compound is observed over a different tyre-life
range. On clean synthetic data the estimator recovers the correct ordering (tests).

Held-out validation (12 held-out 2024 races, curves fitted only from prior 2022+
races):

| metric | DEFAULT curves | FITTED curves |
|---|---|---|
| stop-count hit rate (all 12) | 0.333 | 0.417 |
| winner compound-set hit rate (all 12) | 0.000 | 0.500 |
| stop-count hit rate (dry-only, 10) | 0.400 | 0.400 |
| winner compound-set hit rate (dry-only, 10) | 0.000 | 0.600 |

DECISION: KEEP the labelled defaults; the simulator is unchanged. Although the
fitted curves beat the defaults on the overall metrics, on the fair dry-only
comparison the stop-count metric is a TIE, and the compound ordering is still
physically wrong (SOFT mis-fit vs MEDIUM). The winner-set improvement is largely
an artifact of the defaults being over-conservative (always a 1-stop HARD,HARD),
not evidence the fitted per-compound physics is right. That is not robust enough,
on a 12-race 2024-only sample, to overturn the defaults' correct ordering. The
2022+ fit is persisted as a diagnostic (artifacts/data/tyre_curves.json,
adopted_in_simulator=false). Intermediate/wet keep labelled defaults. The cliff is
largely censored (see reach rate), so the default cliff is kept and labelled.

## Walk-forward over completed [2026] races (separate readout)
Reported separately so it never disturbs the comparable held-out [2025] numbers above. Each [2026] race is predicted after training on every prior race (all earlier seasons plus earlier rounds of the same season), so it is genuinely out-of-sample.

| system | races | spearman | top1 acc | podium acc | mae (positions) |
|---|---|---|---|---|---|
| F1Grid model | 14 | 0.637 | 0.429 | 0.643 | 3.84 |
| Grid-order baseline | 14 | 0.650 | 0.643 | 0.619 | 3.54 |

**Beats grid-order baseline on completed [2026]: NOT YET** (spearman 0.637 vs 0.650).

## Feature importance (race model)
```
grid_position            1.455324
form_avg_points          0.836175
team_points_to_date      0.682968
driver_points_to_date    0.660737
form_avg_grid            0.633824
form_dnf_rate            0.602749
teammate_quali_gap       0.590685
circuit_avg_finish       0.588494
prior_races_count        0.586554
form_avg_finish          0.585508
round_norm               0.581058
```

## Circuit strategy meter (item 2)

A race-level meter describes how much tyre strategy tends to disrupt the order at
a circuit, built ONLY from prior races at that circuit: grid-to-finish
divergence (results), pit-stop-count spread between drivers and safety-car
frequency (lap data, where present). It never uses the fitted degradation curves,
is never fed into the model, and reports a "no history" state for new venues. It
is leakage-checked (reversing a race's own result does not move its meter).

Buckets (Low/Medium/High) were designed on 2023-2024 only (tertiles, frozen),
then tested on held-out 2025 against the hypothesis that high-disruption races
have WORSE prediction error. The relationship did NOT hold; if anything it was
inverted. Per-bucket walk-forward error:

| period | bucket | races | mean Spearman | mean MAE |
|---|---|---|---|---|
| held-out 2025 | Low | 8 | 0.5400 | 4.3688 |
| held-out 2025 | Medium | 9 | 0.6446 | 3.5708 |
| held-out 2025 | High | 7 | 0.6711 | 3.7000 |
| 2026 walk-forward | Low | 6 | 0.5178 | 4.7879 |
| 2026 walk-forward | Medium | 6 | 0.7665 | 2.8485 |
| 2026 walk-forward | High | 1 | 0.5783 | 4.3636 |

High-disruption races were predicted as well or better than low-disruption ones,
so the meter did NOT earn a confidence claim. It is therefore labelled "Strategy
complexity" (a description of the circuit) everywhere, with no confidence wording
in the UI, API, or README. See `f1grid/model/strategy_validate.py` and
`artifacts/eval/strategy_meter.json`.

## Known limitations (stated, not hidden)
- No telemetry/weather features yet beyond the manual rain scenario input.
- Tyre-degradation curves HAVE now been refitted from real FastF1 stint laps on the 2022+ regulation era (see the tyre-degradation-fit section). HARD is now correctly the slowest-degrading, but SOFT and MEDIUM remain inseparable (identification limit), so the compound ordering is still not fully correct. The fitted curves beat the labelled defaults on overall held-out 2024 metrics but tied on the fair dry-only stop-count metric, so the simulator KEEPS the labelled defaults; the fit is persisted as a diagnostic. The cliff is censored and kept as a labelled default. Lap coverage for the fit is 2022-2024 (2024 partial); 2025-2026 pending a FastF1 500-calls/hour rate-limit reset.
- Circuit-level strategy features were built and ablated (item 4). They helped on validation but did not generalize to held-out 2025/2026, so they are NOT in the production model.
- The lap-by-lap strategy simulator models clean air + stochastic safety cars; it does NOT model wheel-to-wheel traffic or undercut/overcut interactions between specific cars.
- The 2026 scenario panel's aero/power-unit dials default to neutral (0.5) because they are not observable from finishing-position data alone; anything beyond that is an explicit, named user override, not a learned value.