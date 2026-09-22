"""2026 data spot-check regression tests (item 5).

Runs on synthetic data (always) to lock the flag logic, and on the real parquet
when present to guard the shipped 2026 data against structural corruption
(duplicate/non-contiguous rounds, inconsistent entry counts, partial data).
"""
from __future__ import annotations

import pandas as pd
import pytest

from f1grid import schema as S
from scripts.spotcheck_2026 import spotcheck, flags
from tests.synthetic import make_synthetic

try:
    from f1grid.data.ingest import load_results
    _REAL = load_results()
    _HAS_2026 = not _REAL[_REAL[S.SEASON] == 2026].empty
except Exception:  # noqa: BLE001
    _REAL, _HAS_2026 = None, False


def test_flags_detect_duplicate_round():
    syn = make_synthetic(seasons=(2026,), rounds_per_season=5)
    df = spotcheck(2026, results=syn)
    dup = pd.concat([df, df.iloc[[0]]], ignore_index=True)
    assert any("DUPLICATE" in f for f in flags(dup))


def test_flags_clean_on_consistent_data():
    syn = make_synthetic(seasons=(2026,), rounds_per_season=5)
    df = spotcheck(2026, results=syn)
    assert any("No structural anomalies" in f for f in flags(df))


@pytest.mark.skipif(not _HAS_2026, reason="no real 2026 data in parquet")
def test_real_2026_is_structurally_sound():
    df = spotcheck(2026, results=_REAL)
    # contiguous rounds from 1, no duplicates
    assert df["round"].tolist() == list(range(1, len(df) + 1))
    assert not df["round"].duplicated().any()
    # every round has a full-ish grid and at least some classified finishers
    assert (df["entries"] > 10).all()
    assert (df["classified"] >= 1).all()
    assert any("No structural anomalies" in f for f in flags(df))
