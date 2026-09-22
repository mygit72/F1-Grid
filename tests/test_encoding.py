"""Encoding regression tests (item 1).

Root cause these guard against: the model card used to be written with
`Path.write_text(card)` and read with `Path.read_text()`, both with NO explicit
encoding. On Windows the default is cp1252, so an em dash was stored as byte 0x97;
on any Linux host (Streamlit Cloud, Railway, Render) the UTF-8 reader then raised
`UnicodeDecodeError: 'utf-8' codec can't decode byte 0x97`.

We now (a) write/read every text artifact as explicit UTF-8, and (b) keep
generated text free of em dashes. These tests lock both in.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from f1grid import train as T
from f1grid.config import EVAL_DIR, PRED_DIR, DATA_DIR

# Characters that must never appear in generated text (they are the exact bytes
# that broke cp1252 -> utf-8 round-trips): em dash and en dash.
_FORBIDDEN = {"—", "–"}


def _sample_card() -> str:
    race_only_summary = pd.DataFrame(
        [
            {"system": "F1Grid model", "races": 21, "spearman": 0.636,
             "top1_acc": 0.52, "podium_acc": 0.68, "mae_pos": 2.50},
            {"system": "Grid-order baseline", "races": 21, "spearman": 0.668,
             "top1_acc": 0.71, "podium_acc": 0.76, "mae_pos": 2.30},
        ]
    )
    importance = pd.Series(
        {"grid_position": 0.42, "form_avg_finish": 0.31, "team_points_to_date": 0.27},
        name="importance",
    )
    e2e = {"spearman": 0.61, "top1_acc": 0.48, "podium_acc": 0.66, "mae_pos": 2.7}
    return T._render_model_card(
        seasons_present=[2019, 2020, 2021, 2022, 2023, 2024, 2025],
        train_seasons=(2019, 2020, 2021, 2022, 2023, 2024),
        eval_seasons=(2025,),
        n_train_rows=2500,
        race_only_summary=race_only_summary,
        e2e_given_grid=e2e,
        e2e_predicted_grid=e2e,
        importance=importance,
        backend="xgboost",
    )


def test_model_card_writes_and_reads_back_strict_utf8(tmp_path: Path):
    """Write the model card and read it back with STRICT UTF-8 decoding.

    Reproduces the original failure mode: had the writer used cp1252 with an em
    dash, `raw.decode("utf-8")` (strict) would raise UnicodeDecodeError here.
    """
    card = _sample_card()
    path = tmp_path / "MODEL_CARD.md"
    path.write_text(card, encoding="utf-8")

    raw = path.read_bytes()
    decoded = raw.decode("utf-8")  # strict by default -> raises on any bad byte
    # Newlines may be platform-translated on write (CRLF on Windows); the point
    # of this test is that the bytes decode as strict UTF-8, which they do here.
    assert decoded.replace("\r\n", "\n") == card

    # Also exercise the exact reader the app/API use (normalizes newlines back).
    assert path.read_text(encoding="utf-8") == card


def test_generated_model_card_has_no_em_dashes():
    """Generated text (the model card) must use plain punctuation only."""
    card = _sample_card()
    for ch in _FORBIDDEN:
        assert ch not in card, f"Model card contains forbidden char {ch!r}"


def test_all_runtime_text_files_decode_as_strict_utf8():
    """Every text file the app/API read at runtime must decode as strict UTF-8.

    This is the regression that catches the shipped MODEL_CARD.md itself: before
    the fix, the committed artifacts/eval/MODEL_CARD.md failed this outright.
    """
    text_suffixes = {".md", ".csv", ".json", ".txt"}
    checked = 0
    problems = []
    for base in (EVAL_DIR, PRED_DIR, DATA_DIR):
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if not p.is_file() or p.suffix.lower() not in text_suffixes:
                continue
            checked += 1
            try:
                p.read_bytes().decode("utf-8")  # strict
            except UnicodeDecodeError as e:
                problems.append(f"{p}: {e}")
    assert not problems, "Non-UTF-8 runtime text files found:\n" + "\n".join(problems)
    # Sanity: the shipped model card should be among the files we checked.
    assert (EVAL_DIR / "MODEL_CARD.md").exists()
    assert checked >= 1
