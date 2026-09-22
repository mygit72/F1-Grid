"""Authoritative race-start lookups for the pre-race publishing boundary.

Reads the schedule artifact written by `f1grid.data.ingest.fetch_schedule`
(season, round, event, race_start_utc). The prediction store uses this to decide
whether a prediction is genuinely pre-race. It is deliberately the ONLY source of
truth for a race's start time: a caller cannot forge it, so the boundary holds
whether a prediction comes from the CLI, the API, or the Streamlit button.
"""
from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache

import pandas as pd

from f1grid.config import SCHEDULE_PARQUET
from f1grid import schema as S

SCHEDULE_FALLBACK = SCHEDULE_PARQUET.with_suffix(".pkl")


def _parse_utc(iso: str | None) -> datetime | None:
    if iso is None or (isinstance(iso, float) and pd.isna(iso)):
        return None
    ts = pd.to_datetime(iso, utc=True)
    if pd.isna(ts):
        return None
    return ts.to_pydatetime()


@lru_cache(maxsize=1)
def _load_schedule_cached(mtime: float) -> pd.DataFrame:
    if SCHEDULE_PARQUET.exists():
        try:
            return pd.read_parquet(SCHEDULE_PARQUET)
        except ImportError:
            pass
    if SCHEDULE_FALLBACK.exists():
        return pd.read_pickle(SCHEDULE_FALLBACK)
    return pd.DataFrame(columns=[S.SEASON, S.ROUND, S.EVENT, "race_start_utc"])


def load_schedule() -> pd.DataFrame:
    """Load the schedule, keyed off file mtime so edits are picked up in-process."""
    for p in (SCHEDULE_PARQUET, SCHEDULE_FALLBACK):
        if p.exists():
            return _load_schedule_cached(p.stat().st_mtime)
    return _load_schedule_cached(0.0)


def race_start_utc(season: int, round_no: int) -> datetime | None:
    """Authoritative UTC race-start for (season, round), or None if unknown."""
    df = load_schedule()
    hit = df[(df[S.SEASON] == season) & (df[S.ROUND] == round_no)]
    if hit.empty:
        return None
    return _parse_utc(hit.iloc[0]["race_start_utc"])


def quali_start_utc(season: int, round_no: int) -> datetime | None:
    """Authoritative UTC start of the session that sets the race grid.

    Used to decide whether a prediction was made pre- or post-qualifying, which
    selects the fair scoring baseline (item 2). None if the schedule predates the
    quali column or has no entry for this race.
    """
    df = load_schedule()
    if "quali_start_utc" not in df.columns:
        return None
    hit = df[(df[S.SEASON] == season) & (df[S.ROUND] == round_no)]
    if hit.empty:
        return None
    return _parse_utc(hit.iloc[0]["quali_start_utc"])


def next_upcoming_race(season: int, now_utc: datetime | None = None) -> dict | None:
    """The earliest race in `season` whose start is strictly in the future."""
    now_utc = now_utc or datetime.now(timezone.utc)
    df = load_schedule()
    df = df[df[S.SEASON] == season].sort_values(S.ROUND)
    for _, r in df.iterrows():
        start = _parse_utc(r["race_start_utc"])
        if start is not None and start > now_utc:
            return {"season": int(r[S.SEASON]), "round": int(r[S.ROUND]),
                    "event": r[S.EVENT], "race_start_utc": start}
    return None
