"""Real data ingestion from FastF1. This is the ONLY module that hits the network.

Run locally (needs internet):
    python -m f1grid.data.ingest --seasons 2019 2020 2021 2022 2023 2024 2025
    python -m f1grid.data.ingest --seasons 2025 --rounds 22 23 24   # backfill
    python -m f1grid.data.ingest --seasons 2026                     # season to date

It produces one tidy parquet of race results keyed by (season, round, driver),
with the starting grid position and the classified finishing position. Everything
downstream reads this parquet and never calls FastF1 again, so feature building
and model training are fully offline and reproducible.

Failure handling (the reason 2025 once stopped mid-season and nobody noticed):
a per-round network/rate-limit error used to be swallowed by a broad
`except ... continue` and the run still exited "successfully" writing a short
season. Now every FUTURE race is skipped explicitly (not a failure), every
PAST scheduled race that fails to ingest is collected and reported LOUDLY at the
end, and `--strict` turns any such gap into a non-zero exit. Transient load
errors are retried with backoff before being counted as failures.
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone

import pandas as pd

from f1grid.config import CONFIG, DATA_DIR, FASTF1_CACHE, SCHEDULE_PARQUET
from f1grid import schema as S

RESULTS_PARQUET = DATA_DIR / "race_results.parquet"
RESULTS_FALLBACK = DATA_DIR / "race_results.pkl"
SCHEDULE_FALLBACK = DATA_DIR / "schedule.pkl"

# How many times to retry a single session load before giving up (the original
# failure was a one-off driver_info fetch error mid-run).
_LOAD_RETRIES = 3
_RETRY_BACKOFF_S = 3.0


def _iso_utc(ts) -> str | None:
    """Normalize a timestamp to an ISO-8601 'Z' UTC string, or None if missing."""
    ts = pd.to_datetime(ts)
    if pd.isna(ts):
        return None
    ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_results(df: pd.DataFrame) -> None:
    """Write parquet; fall back to pickle if pyarrow/fastparquet aren't installed
    (e.g. an offline sandbox). Production environments install pyarrow (see
    requirements.txt) and always get parquet. Parquet/pickle are binary formats;
    pandas/pyarrow encode string columns as UTF-8 internally."""
    try:
        df.to_parquet(RESULTS_PARQUET, index=False)
    except ImportError:
        df.to_pickle(RESULTS_FALLBACK)
        print(f"(pyarrow unavailable - wrote fallback pickle to {RESULTS_FALLBACK})")


def _read_results() -> pd.DataFrame:
    if RESULTS_PARQUET.exists():
        try:
            return pd.read_parquet(RESULTS_PARQUET)
        except ImportError:
            pass
    if RESULTS_FALLBACK.exists():
        return pd.read_pickle(RESULTS_FALLBACK)
    raise FileNotFoundError(
        f"Neither {RESULTS_PARQUET} nor {RESULTS_FALLBACK} found. Run "
        "`python -m f1grid.data.ingest` in a networked environment first."
    )

# Statuses FastF1 reports for a car that was running at the flag. Anything else
# (Accident, Engine, Collision, Retired, +N Laps is still classified...) we treat
# carefully: "+N Lap(s)" and "Finished" are classified finishers; the rest are DNF.
_FINISHED_PREFIXES = ("Finished",)
_LAPPED_MARKER = "Lap"  # e.g. "+1 Lap", "+2 Laps" -> still classified


def _is_dnf(status: str) -> int:
    if status is None:
        return 1
    s = str(status)
    if s.startswith(_FINISHED_PREFIXES):
        return 0
    if _LAPPED_MARKER in s:  # "+1 Lap" etc. -> classified, not a DNF
        return 0
    return 1


def _load_fastf1():
    try:
        import fastf1
    except ImportError:
        sys.exit(
            "fastf1 is not installed. Run `pip install fastf1` in a networked "
            "environment. (This sandbox has no internet, so ingest runs locally.)"
        )
    fastf1.Cache.enable_cache(str(FASTF1_CACHE))
    return fastf1


def _load_session_with_retry(fastf1, season: int, rnd: int):
    """Load a race session, retrying transient failures. Raises on final failure."""
    last_err = None
    for attempt in range(1, _LOAD_RETRIES + 1):
        try:
            session = fastf1.get_session(season, rnd, "R")
            session.load(laps=False, telemetry=False, weather=False, messages=False)
            return session
        except Exception as e:  # noqa: BLE001 - transient network/data gaps expected
            last_err = e
            if attempt < _LOAD_RETRIES:
                print(f"    ... {season} R{rnd} load attempt {attempt} failed "
                      f"({type(e).__name__}: {e}); retrying in {_RETRY_BACKOFF_S}s")
                time.sleep(_RETRY_BACKOFF_S)
    raise last_err


def ingest_season(fastf1, season: int, only_rounds=None, now_utc=None) -> tuple[pd.DataFrame, dict]:
    """Pull every (or selected) race in a season. Returns (rows_df, report).

    report = {
      "failed":         [(round, event, reason), ...],   # PAST races that errored
      "skipped_future": [(round, event, date), ...],     # not yet run -> not a failure
      "ingested_rounds": set[int],                        # rounds we got results for
      "scheduled_past_rounds": set[int],                 # rounds that should exist by now
    }
    """
    now_utc = now_utc or datetime.now(timezone.utc)
    only = set(only_rounds) if only_rounds else None
    schedule = fastf1.get_event_schedule(season, include_testing=False)
    rows: list[dict] = []
    failed, skipped_future = [], []
    ingested_rounds, scheduled_past = set(), set()

    for _, event in schedule.iterrows():
        rnd = int(event["RoundNumber"])
        if rnd < 1:
            continue
        if only is not None and rnd not in only:
            continue
        event_name = event["EventName"]
        event_date = pd.to_datetime(event.get("EventDate"))

        # A race whose date is in the future has legitimately not run yet. This is
        # NOT a failure - it is why "season to date" is shorter than the calendar.
        is_future = pd.notna(event_date) and event_date.to_pydatetime().replace(
            tzinfo=timezone.utc) > now_utc
        if is_future:
            skipped_future.append((rnd, event_name, str(event_date)[:10]))
            continue

        scheduled_past.add(rnd)
        try:
            session = _load_session_with_retry(fastf1, season, rnd)
        except Exception as e:  # noqa: BLE001
            print(f"  ! {season} R{rnd} {event_name}: FAILED ({type(e).__name__}: {e})")
            failed.append((rnd, event_name, f"{type(e).__name__}: {e}"))
            continue

        res = session.results
        if res is None or len(res) == 0:
            print(f"  ! {season} R{rnd} {event_name}: FAILED (no results returned)")
            failed.append((rnd, event_name, "no results returned"))
            continue

        for _, r in res.iterrows():
            grid = r.get("GridPosition")
            pos = r.get("Position")
            status = r.get("Status")
            dnf = _is_dnf(status)
            finish = (
                CONFIG.grid_dnf_position if dnf or pd.isna(pos) else int(pos)
            )
            rows.append({
                S.SEASON: season,
                S.ROUND: rnd,
                S.EVENT: event_name,
                S.DATE: pd.to_datetime(event.get("EventDate")),
                S.DRIVER: r.get("Abbreviation"),
                S.DRIVER_NAME: r.get("FullName"),
                S.TEAM: r.get("TeamName"),
                S.GRID: (
                    CONFIG.grid_dnf_position
                    if pd.isna(grid) or grid == 0 else int(grid)
                ),
                S.FINISH: finish,
                S.STATUS: status,
                S.DNF: dnf,
            })
        ingested_rounds.add(rnd)
        print(f"  + {season} R{rnd} {event_name}: {len(res)} drivers")
        time.sleep(0.3)  # be polite to the cache/backend

    report = {
        "failed": failed,
        "skipped_future": skipped_future,
        "ingested_rounds": ingested_rounds,
        "scheduled_past_rounds": scheduled_past,
    }
    return pd.DataFrame(rows), report


def _merge_into_existing(new_df: pd.DataFrame) -> pd.DataFrame:
    """Merge freshly-ingested rows into the existing parquet, replacing any
    (season, round) that was re-ingested and keeping everything else intact."""
    if new_df.empty:
        return _read_results()
    try:
        existing = _read_results()
    except FileNotFoundError:
        return new_df.sort_values([S.SEASON, S.ROUND, S.FINISH]).reset_index(drop=True)
    new_keys = set(map(tuple, new_df[[S.SEASON, S.ROUND]].drop_duplicates().to_numpy()))
    mask_replaced = existing.apply(
        lambda r: (r[S.SEASON], r[S.ROUND]) in new_keys, axis=1)
    kept = existing[~mask_replaced]
    merged = pd.concat([kept, new_df], ignore_index=True)
    return merged.sort_values([S.SEASON, S.ROUND, S.FINISH]).reset_index(drop=True)


def fetch_schedule(seasons: list[int], fastf1=None) -> pd.DataFrame:
    """Fetch and persist the authoritative race-start schedule for `seasons`.

    Writes (season, round, event, race_start_utc) for EVERY scheduled round
    (past and future) to schedule.parquet. race_start_utc is the Race session
    start in UTC (FastF1 Session5DateUtc), stored as an ISO-8601 'Z' string. The
    prediction store reads this to enforce the pre-race boundary offline; it is
    the single source of truth a caller cannot forge.
    """
    fastf1 = fastf1 or _load_fastf1()
    rows = []
    for season in seasons:
        sched = fastf1.get_event_schedule(season, include_testing=False)
        for _, e in sched.iterrows():
            rnd = int(e["RoundNumber"])
            if rnd < 1:
                continue
            start = e.get("Session5DateUtc")  # Race session start, UTC (naive)
            if pd.isna(start):
                start = e.get("EventDate")     # fall back to event date if needed
            start = pd.to_datetime(start)
            iso = _iso_utc(start)
            # Qualifying start: the session that SETS THE RACE GRID is named
            # exactly "Qualifying" on both conventional and sprint weekends
            # (sprint weekends also have a separate "Sprint Qualifying", which
            # sets only the sprint grid and is deliberately NOT used here). This
            # lets the store/scorer decide whether a prediction was made before
            # or after qualifying, which selects the fair baseline (item 2).
            quali_iso = None
            for i in range(1, 6):
                if str(e.get(f"Session{i}")) == "Qualifying":
                    quali_iso = _iso_utc(pd.to_datetime(e.get(f"Session{i}DateUtc")))
                    break
            rows.append({S.SEASON: season, S.ROUND: rnd,
                         S.EVENT: e["EventName"], "race_start_utc": iso,
                         "quali_start_utc": quali_iso})
    df = pd.DataFrame(rows)
    # Merge with any existing schedule so re-running for one season keeps others.
    if SCHEDULE_PARQUET.exists() or SCHEDULE_FALLBACK.exists():
        try:
            prev = (pd.read_parquet(SCHEDULE_PARQUET) if SCHEDULE_PARQUET.exists()
                    else pd.read_pickle(SCHEDULE_FALLBACK))
            keep = prev[~prev[S.SEASON].isin(seasons)]
            df = pd.concat([keep, df], ignore_index=True)
        except Exception:  # noqa: BLE001
            pass
    df = df.sort_values([S.SEASON, S.ROUND]).reset_index(drop=True)
    try:
        df.to_parquet(SCHEDULE_PARQUET, index=False)
    except ImportError:
        df.to_pickle(SCHEDULE_FALLBACK)
    print(f"Wrote schedule for seasons {seasons} ({len(df)} total rows).")
    return df


def ingest(seasons: list[int], only_rounds=None, merge: bool = True,
           strict: bool = False, now_utc=None) -> pd.DataFrame:
    """Ingest `seasons` (optionally restricted to `only_rounds`), reporting any
    failed/missing PAST races loudly. With merge=True the result is folded into
    the existing parquet instead of overwriting it."""
    fastf1 = _load_fastf1()
    now_utc = now_utc or datetime.now(timezone.utc)
    # Refresh the authoritative race-start schedule for these seasons.
    try:
        fetch_schedule(seasons, fastf1=fastf1)
    except Exception as e:  # noqa: BLE001 - schedule is best-effort; data is primary
        print(f"WARNING: could not refresh schedule ({type(e).__name__}: {e})")
    frames, all_reports = [], {}
    for season in seasons:
        print(f"== Season {season} ==")
        df_s, report = ingest_season(fastf1, season, only_rounds=only_rounds, now_utc=now_utc)
        if not df_s.empty:
            frames.append(df_s)
        all_reports[season] = report

    new_df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    final = _merge_into_existing(new_df) if merge else (
        new_df.sort_values([S.SEASON, S.ROUND, S.FINISH]).reset_index(drop=True)
        if not new_df.empty else _read_results())

    _write_results(final)

    # ── LOUD end-of-run report ──────────────────────────────────────────────
    print("\n" + "=" * 64)
    print("INGEST SUMMARY")
    print("=" * 64)
    total_missing = 0
    present_by_season = (
        final.groupby(S.SEASON)[S.ROUND].apply(lambda s: set(s.unique()))
        if not final.empty else {}
    )
    for season in seasons:
        rep = all_reports[season]
        present = present_by_season.get(season, set()) if len(present_by_season) else set()
        expected_past = rep["scheduled_past_rounds"]
        missing = sorted(expected_past - present)
        total_missing += len(missing)
        print(f"Season {season}: {len(present)} rounds present, "
              f"{len(rep['skipped_future'])} future rounds skipped, "
              f"{len(rep['failed'])} failed this run.")
        if rep["failed"]:
            for rnd, name, reason in rep["failed"]:
                print(f"   FAILED  R{rnd:02d} {name}: {reason}")
        if missing:
            print(f"   !! MISSING PAST RACES for {season}: rounds {missing} "
                  f"are scheduled and already run but NOT in the dataset.")
    print("=" * 64)
    print(f"Wrote {len(final):,} rows total.")

    if total_missing and strict:
        raise RuntimeError(
            f"Ingestion incomplete: {total_missing} past race(s) missing. "
            "Re-run ingest for those rounds (a transient network/rate-limit error "
            "is the usual cause) or drop --strict to write what was collected.")
    if total_missing:
        print(f"WARNING: {total_missing} past race(s) still missing - see above.")
    return final


def load_results() -> pd.DataFrame:
    """Read cached results. Downstream modules use this, never FastF1 directly."""
    return _read_results()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--seasons", type=int, nargs="+",
        default=list(CONFIG.train_seasons) + list(CONFIG.eval_seasons),
    )
    ap.add_argument("--rounds", type=int, nargs="+", default=None,
                    help="Restrict to these round numbers (across each --seasons entry).")
    ap.add_argument("--no-merge", action="store_true",
                    help="Overwrite the parquet instead of merging into it.")
    ap.add_argument("--strict", action="store_true",
                    help="Exit non-zero if any past scheduled race is missing.")
    args = ap.parse_args()
    ingest(args.seasons, only_rounds=args.rounds, merge=not args.no_merge,
           strict=args.strict)


if __name__ == "__main__":
    main()
