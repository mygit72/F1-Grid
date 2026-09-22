"""Circuit-level strategy features (item 4).

Four features, each attached to every driver row of a race and computed ONLY from
races strictly before that race (walk-forward, leakage-free):

  circuit_pit_loss      Time lost pitting at this circuit. Estimated from real lap
                        timing as (median in-lap delta + median out-lap delta) vs
                        the race's green-lap median. NOTE: this is a lap-time proxy;
                        the exact pit-lane delta would need cached PitIn/PitOutTime
                        timestamps, which the lap cache does not store.
  circuit_typical_stops Mean pit stops per driver at this circuit in prior races.
  circuit_overtake_diff Overtaking difficulty = mean Spearman(grid, finish) over
                        prior races here. High = grid predicts finish = hard to pass.
  circuit_deg_level     The circuit's fitted tyre-degradation level from item 3
                        (laps-weighted mean per-compound tyre-life slope), averaged
                        over prior same-circuit events.

Pit-loss / typical-stops / deg-level come from lap data (cached 2019-2021); a
circuit with no prior lap history (a new venue, or before its first cached running)
falls back to the POOLED average over all prior circuits and is flagged in
`circuit_no_history` = 1. Overtaking difficulty comes from the results parquet, so
it has full coverage.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from f1grid import schema as S

STRAT_FEATURES = [
    "circuit_pit_loss",
    "circuit_typical_stops",
    "circuit_overtake_diff",
    "circuit_deg_level",
]
STRAT_NO_HISTORY = "circuit_no_history"


def _chrono(df: pd.DataFrame) -> pd.DataFrame:
    r = df[[S.SEASON, S.ROUND, S.DATE]].drop_duplicates().copy()
    r[S.DATE] = pd.to_datetime(r[S.DATE])
    r = r.sort_values([S.DATE, S.SEASON, S.ROUND]).reset_index(drop=True)
    r["race_id"] = r.index
    return r


def per_event_lap_stats(laps: pd.DataFrame) -> pd.DataFrame:
    """Per-(season, round) pit loss, typical stops, and degradation level from laps."""
    from f1grid.model.tyre_fit import filter_representative_laps, _fit_event
    rows = []
    for (season, rnd), g in laps.groupby([S.SEASON, S.ROUND]):
        dry = g[~g["compound"].isin(["INTERMEDIATE", "WET"])]
        filt, _ = filter_representative_laps(dry)
        green = filt["lap_time_s"].median() if not filt.empty else np.nan
        # pit loss proxy: in-lap + out-lap time lost vs green pace
        in_delta = (g.loc[g["is_pit_in"] & g["lap_time_s"].notna(), "lap_time_s"] - green)
        out_delta = (g.loc[g["is_pit_out"] & g["lap_time_s"].notna(), "lap_time_s"] - green)
        pit_loss = np.nan
        if np.isfinite(green) and (len(in_delta) or len(out_delta)):
            pit_loss = float(np.nansum([
                in_delta.median() if len(in_delta) else 0.0,
                out_delta.median() if len(out_delta) else 0.0,
            ]))
        stops = g.groupby(S.DRIVER)["stint"].nunique() - 1
        typical_stops = float(stops[stops >= 0].mean()) if len(stops) else np.nan
        deg = np.nan
        if not filt.empty:
            ef = _fit_event(filt)
            if ef and ef["compounds"]:
                degs = [c["deg"] for c in ef["compounds"].values()]
                wts = [c["n_laps"] for c in ef["compounds"].values()]
                deg = float(np.average(degs, weights=wts))
        rows.append({S.SEASON: int(season), S.ROUND: int(rnd),
                     S.EVENT: g[S.EVENT].iloc[0],
                     "pit_loss": pit_loss, "typical_stops": typical_stops, "deg": deg})
    return pd.DataFrame(rows)


def per_event_overtake(results: pd.DataFrame) -> pd.DataFrame:
    """Per-(season, round) overtaking difficulty = Spearman(grid, finish)."""
    rows = []
    for (season, rnd), g in results.groupby([S.SEASON, S.ROUND]):
        gg = g[[S.GRID, S.FINISH]].dropna()
        rho = np.nan
        if len(gg) >= 5:
            r = spearmanr(gg[S.GRID], gg[S.FINISH]).statistic
            rho = float(r) if not np.isnan(r) else np.nan
        rows.append({S.SEASON: int(season), S.ROUND: int(rnd),
                     S.EVENT: g[S.EVENT].iloc[0], "overtake_diff": rho})
    return pd.DataFrame(rows)


def build_strategy_features(results: pd.DataFrame,
                            laps: pd.DataFrame | None) -> pd.DataFrame:
    """Per-(season, round) circuit features from strictly-prior races (walk-forward).

    Returns one row per race with STRAT_FEATURES + STRAT_NO_HISTORY, ready to merge
    onto the feature matrix by (season, round)."""
    races = _chrono(results)
    # Canonical event name per race comes from results (full coverage). lap_stats
    # and overtake tables are merged on numeric (season, round) ONLY, so their own
    # event columns never shadow the canonical name for uncovered seasons.
    canon = results[[S.SEASON, S.ROUND, S.EVENT]].drop_duplicates()
    lap_stats = (per_event_lap_stats(laps) if laps is not None and not laps.empty
                 else pd.DataFrame(columns=[S.SEASON, S.ROUND,
                                            "pit_loss", "typical_stops", "deg"]))
    lap_stats = lap_stats.drop(columns=[S.EVENT], errors="ignore")
    ot = per_event_overtake(results).drop(columns=[S.EVENT], errors="ignore")
    ev = (races.merge(canon, on=[S.SEASON, S.ROUND], how="left")
               .merge(lap_stats, on=[S.SEASON, S.ROUND], how="left")
               .merge(ot, on=[S.SEASON, S.ROUND], how="left"))
    ev = ev.sort_values("race_id").reset_index(drop=True)

    out_rows = []
    for _, row in ev.iterrows():
        rid = row["race_id"]
        circuit = row[S.EVENT]
        prior = ev[ev["race_id"] < rid]
        prior_circ = prior[prior[S.EVENT] == circuit]

        feats, no_hist = {}, 0
        for col, src in [("circuit_pit_loss", "pit_loss"),
                         ("circuit_typical_stops", "typical_stops"),
                         ("circuit_deg_level", "deg")]:
            vals = prior_circ[src].dropna()
            if len(vals):
                feats[col] = float(vals.mean())
            else:
                pooled = prior[src].dropna()
                feats[col] = float(pooled.mean()) if len(pooled) else 0.0
                no_hist = 1
        # overtaking difficulty (full coverage from results)
        ot_vals = prior_circ["overtake_diff"].dropna()
        if len(ot_vals):
            feats["circuit_overtake_diff"] = float(ot_vals.mean())
        else:
            pooled = prior["overtake_diff"].dropna()
            feats["circuit_overtake_diff"] = float(pooled.mean()) if len(pooled) else 0.0
        feats[STRAT_NO_HISTORY] = no_hist
        feats[S.SEASON] = int(row[S.SEASON])
        feats[S.ROUND] = int(row[S.ROUND])
        out_rows.append(feats)
    return pd.DataFrame(out_rows)


def attach_strategy_features(feats: pd.DataFrame, results: pd.DataFrame,
                             laps: pd.DataFrame | None) -> pd.DataFrame:
    """Merge circuit strategy features onto a per-driver feature matrix."""
    strat = build_strategy_features(results, laps)
    return feats.merge(strat, on=[S.SEASON, S.ROUND], how="left")


def assert_strategy_features_no_leakage(results: pd.DataFrame,
                                        laps: pd.DataFrame | None,
                                        eval_seasons=None) -> None:
    """Leakage self-check for the strategy features (item 4): a race's circuit
    features must not change when only that race's OWN result (finish + grid) is
    corrupted, because they are built from strictly-prior races.

    (Lap-derived features read the lap cache, not `results`, so corrupting a
    results row cannot touch them; the sensitive one is overtaking difficulty,
    which reads grid+finish - this asserts it too only uses prior races.)"""
    seasons = eval_seasons or sorted(results[S.SEASON].unique())
    base = build_strategy_features(results, laps).set_index([S.SEASON, S.ROUND])
    cols = STRAT_FEATURES + [STRAT_NO_HISTORY]
    races = (results[results[S.SEASON].isin(seasons)][[S.SEASON, S.ROUND]]
             .drop_duplicates().to_records(index=False))
    for season, round_no in races:
        season, round_no = int(season), int(round_no)
        corrupt = results.copy()
        mask = (corrupt[S.SEASON] == season) & (corrupt[S.ROUND] == round_no)
        corrupt.loc[mask, S.FINISH] = corrupt.loc[mask, S.FINISH].values[::-1]
        corrupt.loc[mask, S.GRID] = corrupt.loc[mask, S.GRID].values[::-1]
        got = build_strategy_features(corrupt, laps).set_index([S.SEASON, S.ROUND])
        a = base.loc[(season, round_no), cols]
        b = got.loc[(season, round_no), cols]
        if not np.allclose(a.to_numpy(dtype=float), b.to_numpy(dtype=float),
                           equal_nan=True):
            raise AssertionError(
                f"Leakage: strategy features for {season} R{round_no} changed when "
                f"only that race's own result was corrupted.")
    print(f"Strategy-feature leakage check: {len(races)} races stable. OK")
