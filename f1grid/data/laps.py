"""Lap-level ingestion from FastF1 for tyre-degradation fitting (item 3).

This is the second module (besides `data.ingest`) that hits the network. It loads
lap-level timing for every race already in the results parquet and extracts a tidy
per-(race, driver, lap) frame with exactly the fields the tyre fit needs:

    season, round, event_name, event_date, driver, team,
    lap_number, lap_time_s, stint, compound, tyre_life,
    is_pit_in, is_pit_out, track_status, is_accurate, position, race_is_wet

Nothing here fabricates data. If a race's laps cannot be downloaded, the failure
is reported and that race is skipped (the fit then simply uses fewer stints).

The output parquet (`artifacts/data/laps.parquet`) is a large derived cache and is
NOT committed to git; only the fitted-curve SUMMARY (data/tyre_curves.json) is.

Run locally (needs internet):
    python -m f1grid.data.laps                 # all races in the results parquet
    python -m f1grid.data.laps --seasons 2024 2025
"""
from __future__ import annotations

import argparse
import time
from datetime import datetime, timezone

import pandas as pd

from f1grid.config import DATA_DIR, FASTF1_CACHE
from f1grid import schema as S
from f1grid.data.ingest import load_results, _load_fastf1

LAPS_PARQUET = DATA_DIR / "laps.parquet"
LAPS_FALLBACK = DATA_DIR / "laps.pkl"

_LOAD_RETRIES = 3
_RETRY_BACKOFF_S = 3.0
_WET_COMPOUNDS = {"INTERMEDIATE", "WET"}


def _read_laps() -> pd.DataFrame:
    if LAPS_PARQUET.exists():
        try:
            return pd.read_parquet(LAPS_PARQUET)
        except ImportError:
            pass
    if LAPS_FALLBACK.exists():
        return pd.read_pickle(LAPS_FALLBACK)
    return pd.DataFrame()


def _write_laps(df: pd.DataFrame) -> None:
    try:
        df.to_parquet(LAPS_PARQUET, index=False)
    except ImportError:
        df.to_pickle(LAPS_FALLBACK)


def _load_race_laps(fastf1, season: int, rnd: int):
    """Load a race session WITH laps + weather, retrying transient failures."""
    last_err = None
    for attempt in range(1, _LOAD_RETRIES + 1):
        try:
            sess = fastf1.get_session(season, rnd, "R")
            # weather=False keeps the per-race API-call count down (the FastF1
            # backend enforces 500 calls/hour); the race-level wet flag is derived
            # from whether intermediate/wet compounds were actually run.
            sess.load(laps=True, telemetry=False, weather=False, messages=False)
            return sess
        except Exception as e:  # noqa: BLE001
            last_err = e
            if attempt < _LOAD_RETRIES:
                print(f"    ... {season} R{rnd} laps attempt {attempt} failed "
                      f"({type(e).__name__}: {e}); retrying in {_RETRY_BACKOFF_S}s")
                time.sleep(_RETRY_BACKOFF_S)
    raise last_err


def _extract_session(sess, season, rnd, event, event_date) -> pd.DataFrame:
    laps = sess.laps
    if laps is None or len(laps) == 0:
        return pd.DataFrame()

    # Race-level wet flag: any intermediate/wet running (derived from compound,
    # so no extra weather API call is needed).
    comp_upper = laps["Compound"].astype("string").str.upper()
    race_is_wet = bool(comp_upper.isin(_WET_COMPOUNDS).any())

    rows = []
    for _, lp in laps.iterrows():
        lt = lp.get("LapTime")
        lap_time_s = float(lt.total_seconds()) if pd.notna(lt) else None
        tl = lp.get("TyreLife")
        stint = lp.get("Stint")
        ln = lp.get("LapNumber")
        pos = lp.get("Position")
        rows.append({
            S.SEASON: season,
            S.ROUND: rnd,
            S.EVENT: event,
            S.DATE: event_date,
            S.DRIVER: lp.get("Driver"),
            S.TEAM: lp.get("Team"),
            "lap_number": int(ln) if pd.notna(ln) else None,
            "lap_time_s": lap_time_s,
            "stint": int(stint) if pd.notna(stint) else None,
            "compound": (str(lp.get("Compound")).upper()
                         if pd.notna(lp.get("Compound")) else None),
            "tyre_life": float(tl) if pd.notna(tl) else None,
            "is_pit_in": bool(pd.notna(lp.get("PitInTime"))),
            "is_pit_out": bool(pd.notna(lp.get("PitOutTime"))),
            "track_status": (str(lp.get("TrackStatus"))
                             if pd.notna(lp.get("TrackStatus")) else None),
            "is_accurate": bool(lp.get("IsAccurate")) if pd.notna(lp.get("IsAccurate")) else False,
            "position": float(pos) if pd.notna(pos) else None,
            "race_is_wet": race_is_wet,
        })
    return pd.DataFrame(rows)


def download_laps(seasons=None, only_rounds=None, resume: bool = True) -> pd.DataFrame:
    """Download + extract lap-level data for races in the results parquet.

    resume=True skips any (season, round) already present in laps.parquet, so a
    long run can be restarted. Returns the full accumulated laps frame.
    """
    fastf1 = _load_fastf1()
    results = load_results()
    keys = (results[[S.SEASON, S.ROUND, S.EVENT, S.DATE]]
            .drop_duplicates()
            .sort_values([S.SEASON, S.ROUND]))
    if seasons:
        keys = keys[keys[S.SEASON].isin(seasons)]
    if only_rounds:
        keys = keys[keys[S.ROUND].isin(only_rounds)]

    existing = _read_laps() if resume else pd.DataFrame()
    done = set()
    if not existing.empty:
        done = set(map(tuple, existing[[S.SEASON, S.ROUND]].drop_duplicates().to_numpy()))

    frames = [existing] if not existing.empty else []
    failed = []
    total = len(keys)
    for i, (_, k) in enumerate(keys.iterrows(), 1):
        season, rnd = int(k[S.SEASON]), int(k[S.ROUND])
        if (season, rnd) in done:
            continue
        event, event_date = k[S.EVENT], k[S.DATE]
        try:
            sess = _load_race_laps(fastf1, season, rnd)
            df = _extract_session(sess, season, rnd, event, event_date)
        except Exception as e:  # noqa: BLE001
            print(f"  ! {season} R{rnd:02d} {event}: FAILED ({type(e).__name__}: {e})")
            failed.append((season, rnd, event, f"{type(e).__name__}: {e}"))
            continue
        if df.empty:
            print(f"  ! {season} R{rnd:02d} {event}: no laps returned")
            failed.append((season, rnd, event, "no laps returned"))
            continue
        frames.append(df)
        print(f"  + {season} R{rnd:02d} {event}: {len(df)} laps "
              f"({i}/{total})")
        # Persist incrementally so a crash mid-run keeps progress.
        _write_laps(pd.concat(frames, ignore_index=True))
        time.sleep(0.2)

    final = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    _write_laps(final)
    print("\n" + "=" * 60)
    print(f"LAP DOWNLOAD DONE: {final[[S.SEASON, S.ROUND]].drop_duplicates().shape[0] if not final.empty else 0} "
          f"races, {len(final):,} laps total. {len(failed)} failed this run.")
    for season, rnd, event, reason in failed:
        print(f"   FAILED {season} R{rnd:02d} {event}: {reason}")
    print("=" * 60)
    return final


def load_laps() -> pd.DataFrame:
    df = _read_laps()
    if df.empty:
        raise FileNotFoundError(
            f"No lap cache at {LAPS_PARQUET}. Run `python -m f1grid.data.laps` "
            "in a networked environment first.")
    return df


def main():
    ap = argparse.ArgumentParser(description="Download lap-level data for tyre fitting.")
    ap.add_argument("--seasons", type=int, nargs="+", default=None)
    ap.add_argument("--rounds", type=int, nargs="+", default=None)
    ap.add_argument("--no-resume", action="store_true")
    args = ap.parse_args()
    download_laps(seasons=args.seasons, only_rounds=args.rounds,
                  resume=not args.no_resume)


if __name__ == "__main__":
    main()
