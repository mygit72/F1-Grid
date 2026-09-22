"""Fair baselines for a prediction made BEFORE qualifying (item 2).

The grid-order baseline (predict finish = starting grid) is only available AFTER
qualifying. A prediction published before qualifying is being compared against
information it could not have had. These two baselines use ONLY information
available at the same moment as a pre-qualifying prediction (results of races
strictly before this one):

  championship_standings_order
      Rank drivers by their season-to-date championship points over the rounds
      already run this season (rounds < R). Ties - including every driver on zero
      points at the season opener - are broken by the previous-race-order baseline,
      then by driver code for full determinism.

  previous_race_order
      Rank drivers by their finishing position in the immediately preceding race
      on the calendar (the chronologically previous round, which at a season opener
      is the previous season's finale).
      Drivers in this race's lineup who did NOT start that previous race are a
      documented, explicit case:
        - tier 0: started the previous race        -> ranked by that finish
        - tier 1: did not, but ran some earlier race -> ranked AFTER tier 0 by
                  their most recent prior finish
        - tier 2: true debut, no prior race at all  -> placed at the very back
      Within a tier, ties break by finishing position then driver code.

Both read only rounds strictly before R, so neither can see the race's own result;
this is asserted directly by `assert_baselines_no_leakage`.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from f1grid import schema as S

_DEBUT_SENTINEL = 999  # sorts a true debutant behind everyone with any history


def _chrono_races(results: pd.DataFrame) -> pd.DataFrame:
    r = results[[S.SEASON, S.ROUND, S.DATE]].drop_duplicates().copy()
    r[S.DATE] = pd.to_datetime(r[S.DATE])
    r = r.sort_values([S.DATE, S.SEASON, S.ROUND]).reset_index(drop=True)
    r["race_id"] = r.index
    return r


def _race_id(races: pd.DataFrame, season: int, round_no: int):
    hit = races[(races[S.SEASON] == season) & (races[S.ROUND] == round_no)]
    return None if hit.empty else int(hit["race_id"].iloc[0])


def _lineup(results: pd.DataFrame, season: int, round_no: int) -> list[str]:
    return (results[(results[S.SEASON] == season) & (results[S.ROUND] == round_no)]
            [S.DRIVER].drop_duplicates().tolist())


def _as_order(drivers: list[str]) -> pd.DataFrame:
    return pd.DataFrame({S.DRIVER: drivers,
                         "predicted_position": np.arange(1, len(drivers) + 1)})


def previous_race_order(results: pd.DataFrame, season: int, round_no: int,
                        lineup: list[str] | None = None) -> pd.DataFrame:
    """Predicted order = the previous race's finishing order (see module docstring)."""
    results = results.copy()
    results[S.DATE] = pd.to_datetime(results[S.DATE])
    races = _chrono_races(results)
    rid = _race_id(races, season, round_no)
    if rid is None:
        raise ValueError(f"{season} R{round_no} not found in results.")
    resid = results.merge(races[[S.SEASON, S.ROUND, "race_id"]],
                          on=[S.SEASON, S.ROUND], how="left")
    if lineup is None:
        lineup = _lineup(results, season, round_no)

    prev = resid[resid["race_id"] == rid - 1] if rid >= 1 else resid.iloc[0:0]
    prev_finish = dict(zip(prev[S.DRIVER], prev[S.FINISH]))

    hist = resid[resid["race_id"] < rid].sort_values("race_id")
    last_known = hist.groupby(S.DRIVER)[S.FINISH].last().to_dict()

    keyed = []
    for drv in lineup:
        if drv in prev_finish:
            keyed.append((0, float(prev_finish[drv]), drv))
        elif drv in last_known:
            keyed.append((1, float(last_known[drv]), drv))
        else:
            keyed.append((2, float(_DEBUT_SENTINEL), drv))
    keyed.sort(key=lambda t: (t[0], t[1], t[2]))
    return _as_order([drv for _, _, drv in keyed])


def championship_standings_order(results: pd.DataFrame, season: int, round_no: int,
                                 lineup: list[str] | None = None) -> pd.DataFrame:
    """Predicted order = season-to-date championship standings (see module docstring)."""
    results = results.copy()
    if lineup is None:
        lineup = _lineup(results, season, round_no)

    season_hist = results[(results[S.SEASON] == season) &
                          (results[S.ROUND] < round_no)].copy()
    season_hist["points"] = season_hist[S.FINISH].apply(S.points_for)
    pts = season_hist.groupby(S.DRIVER)["points"].sum().to_dict()

    prev = previous_race_order(results, season, round_no, lineup=lineup)
    prev_rank = dict(zip(prev[S.DRIVER], prev["predicted_position"]))

    keyed = [(-float(pts.get(drv, 0.0)), int(prev_rank.get(drv, _DEBUT_SENTINEL)), drv)
             for drv in lineup]
    keyed.sort(key=lambda t: (t[0], t[1], t[2]))
    return _as_order([drv for _, _, drv in keyed])


# Registry so callers can iterate the pre-qualifying baselines by name.
PRE_QUALIFYING_BASELINES = {
    "championship_standings": championship_standings_order,
    "previous_race": previous_race_order,
}


def assert_baselines_no_leakage(results: pd.DataFrame, eval_seasons=None) -> None:
    """Direct leakage check: a baseline's order for race R must not change when
    R's own finishing positions are corrupted (reversed). Because the baselines
    read only rounds < R, the order must be byte-for-byte identical."""
    results = results.copy()
    results[S.DATE] = pd.to_datetime(results[S.DATE])
    seasons = eval_seasons or sorted(results[S.SEASON].unique())
    races = (results[results[S.SEASON].isin(seasons)][[S.SEASON, S.ROUND]]
             .drop_duplicates().to_records(index=False))

    for season, round_no in races:
        season, round_no = int(season), int(round_no)
        # Corrupt ONLY this race's own finishing positions; every other race
        # (including the previous round the baselines legitimately read) is left
        # untouched, so any change proves the baseline peeked at R's own result.
        corrupted = results.copy()
        mask = (corrupted[S.SEASON] == season) & (corrupted[S.ROUND] == round_no)
        corrupted.loc[mask, S.FINISH] = corrupted.loc[mask, S.FINISH].values[::-1]
        for name, fn in PRE_QUALIFYING_BASELINES.items():
            a = fn(results, season, round_no)
            b = fn(corrupted, season, round_no)
            if not a.equals(b):
                raise AssertionError(
                    f"Leakage: baseline {name!r} for {season} R{round_no} changed "
                    f"when only that race's own result was corrupted.")
    print(f"Baseline leakage check: {len(races)} races x "
          f"{len(PRE_QUALIFYING_BASELINES)} pre-qualifying baselines stable. OK")
