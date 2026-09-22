"""Ingestion loud-reporting regression tests (item 5).

Root cause guarded against: a per-round network/rate-limit error mid-season was
swallowed by a broad `except ... continue`, and the run still exited
"successfully" writing a short season (2025 stopped at R21, missing Las Vegas /
Qatar / Abu Dhabi). Ingestion now distinguishes FUTURE races (not yet run) from
genuine FAILURES, and reports any missing PAST race loudly - with `--strict`
turning a gap into a hard error.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from f1grid.data import ingest as ing
from f1grid import schema as S

NOW = datetime(2026, 9, 21, tzinfo=timezone.utc)


def _results_frame(n=20):
    return pd.DataFrame({
        "Abbreviation": [f"D{i:02d}" for i in range(n)],
        "FullName": [f"Driver {i}" for i in range(n)],
        "TeamName": ["Cadillac" if i < 2 else "Ferrari" for i in range(n)],
        "GridPosition": list(range(1, n + 1)),
        "Position": list(range(1, n + 1)),
        "Status": ["Finished"] * n,
    })


class _FakeSession:
    def __init__(self, results, fail=False):
        self._results, self._fail = results, fail

    def load(self, **kw):
        if self._fail:
            raise RuntimeError("driver_info fetch failed (simulated rate limit)")

    @property
    def results(self):
        return self._results


class _FakeFastF1:
    def __init__(self, schedule, sessions):
        self._schedule, self._sessions = schedule, sessions

    def get_event_schedule(self, season, include_testing=False):
        return self._schedule

    def get_session(self, season, rnd, code):
        return self._sessions[(season, rnd)]


@pytest.fixture()
def fast_retries(monkeypatch):
    # Don't actually sleep through retry backoff in tests.
    monkeypatch.setattr(ing.time, "sleep", lambda *a, **k: None)


def _schedule():
    return pd.DataFrame({
        "RoundNumber": [1, 2, 3],
        "EventName": ["Good GP", "Failing GP", "Future GP"],
        "EventDate": [pd.Timestamp("2026-03-01"), pd.Timestamp("2026-03-08"),
                      pd.Timestamp("2026-12-01")],  # R3 is after NOW
    })


def test_ingest_season_categorizes_future_failed_and_success(fast_retries):
    sessions = {
        (2026, 1): _FakeSession(_results_frame()),
        (2026, 2): _FakeSession(None, fail=True),      # past race that errors
        (2026, 3): _FakeSession(_results_frame()),      # future -> never loaded
    }
    fake = _FakeFastF1(_schedule(), sessions)
    df, report = ing.ingest_season(fake, 2026, now_utc=NOW)

    assert report["ingested_rounds"] == {1}
    assert [r[0] for r in report["failed"]] == [2]
    assert [r[0] for r in report["skipped_future"]] == [3]
    assert report["scheduled_past_rounds"] == {1, 2}  # R3 is future, not "past"
    assert set(df[S.ROUND].unique()) == {1}


def test_ingest_strict_raises_on_missing_past_race(fast_retries, monkeypatch, tmp_path):
    sessions = {
        (2026, 1): _FakeSession(_results_frame()),
        (2026, 2): _FakeSession(None, fail=True),
        (2026, 3): _FakeSession(_results_frame()),
    }
    fake = _FakeFastF1(_schedule(), sessions)
    monkeypatch.setattr(ing, "_load_fastf1", lambda: fake)
    monkeypatch.setattr(ing, "_write_results", lambda df: None)
    # ISOLATION: ingest() refreshes the authoritative schedule as a side effect.
    # Redirect that write to tmp so the test can never clobber the real
    # artifacts/data/schedule.parquet (which previously wiped the real 2026
    # calendar down to the synthetic "Good/Failing/Future GP" fixture rows).
    monkeypatch.setattr(ing, "SCHEDULE_PARQUET", tmp_path / "schedule.parquet")
    monkeypatch.setattr(ing, "SCHEDULE_FALLBACK", tmp_path / "schedule.pkl")
    # No existing parquet -> merge falls back to just the new rows.
    monkeypatch.setattr(ing, "_read_results",
                        lambda: (_ for _ in ()).throw(FileNotFoundError()))

    with pytest.raises(RuntimeError, match="Ingestion incomplete"):
        ing.ingest([2026], merge=True, strict=True, now_utc=NOW)

    # Without strict it must still complete (write what it has) and not raise.
    out = ing.ingest([2026], merge=True, strict=False, now_utc=NOW)
    assert set(out[S.ROUND].unique()) == {1}


def test_merge_replaces_only_reingested_rounds(monkeypatch):
    existing = pd.DataFrame({
        S.SEASON: [2025, 2025, 2025], S.ROUND: [1, 2, 21],
        S.EVENT: ["a", "b", "c"], S.DATE: pd.Timestamp("2025-01-01"),
        S.DRIVER: ["X", "Y", "Z"], S.DRIVER_NAME: ["X", "Y", "Z"],
        S.TEAM: ["T", "T", "T"], S.GRID: [1, 2, 3], S.FINISH: [1, 2, 3],
        S.STATUS: ["Finished"] * 3, S.DNF: [0, 0, 0],
    })
    monkeypatch.setattr(ing, "_read_results", lambda: existing)
    new = existing.iloc[[2]].copy()
    new[S.ROUND] = 22   # a brand new round to append
    new[S.DRIVER] = "W"
    merged = ing._merge_into_existing(new)
    # Original rounds preserved, new round added.
    assert set(merged[S.ROUND].unique()) == {1, 2, 21, 22}
    assert len(merged) == 4
