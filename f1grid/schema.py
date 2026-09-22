"""Canonical column names. Importing these instead of hardcoding strings keeps
the data contract consistent across ingest, features, model, and scoring.

The cardinal rule of this project:
    A feature describing race R may ONLY use information available BEFORE race R
    starts (results from rounds < R, plus qualifying for R itself, which happens
    before the race). Anything computed from race R's own result is a LABEL, never
    a feature. The feature builder enforces this by construction.
"""
from __future__ import annotations

# ── Identity / keys ───────────────────────────────────────────────────────────
SEASON = "season"
ROUND = "round"
EVENT = "event_name"
DATE = "event_date"
DRIVER = "driver"            # 3-letter code, e.g. "VER"
DRIVER_NAME = "driver_name"
TEAM = "team"

# ── Pre-race signal (known before lights out) ─────────────────────────────────
GRID = "grid_position"       # from qualifying / starting grid

# ── Label (known only AFTER the race) ─────────────────────────────────────────
FINISH = "finish_position"   # classified finishing position (DNF -> sentinel)
STATUS = "status"            # raw FastF1 status string
DNF = "dnf"                  # 1 if did not finish

# ── Engineered features (all strictly as-of pre-race) ─────────────────────────
F_GRID = "grid_position"
F_FORM_FINISH = "form_avg_finish"        # mean finish over last N prior races
F_FORM_GRID = "form_avg_grid"            # mean grid over last N prior races
F_FORM_POINTS = "form_avg_points"        # mean points over last N prior races
F_DNF_RATE = "form_dnf_rate"             # DNF rate over prior races this season
F_TEAM_PTS_TD = "team_points_to_date"    # team season-to-date points before R
F_DRV_PTS_TD = "driver_points_to_date"   # driver season-to-date points before R
F_CIRCUIT_HIST = "circuit_avg_finish"    # driver mean finish at this circuit (prior yrs)
F_TEAMMATE_GAP = "teammate_quali_gap"    # grid delta vs teammate this race
F_ROUND_NORM = "round_norm"              # round / total_rounds (season progress)
F_PRIOR_EXP = "prior_races_count"        # races completed before this one

FEATURE_COLUMNS = [
    F_GRID,
    F_FORM_FINISH,
    F_FORM_GRID,
    F_FORM_POINTS,
    F_DNF_RATE,
    F_TEAM_PTS_TD,
    F_DRV_PTS_TD,
    F_CIRCUIT_HIST,
    F_TEAMMATE_GAP,
    F_ROUND_NORM,
    F_PRIOR_EXP,
]

# F1 points for a finishing position (no fastest-lap / sprint handling here;
# kept deliberately simple and explicit).
POINTS_BY_POSITION = {1: 25, 2: 18, 3: 15, 4: 12, 5: 10,
                      6: 8, 7: 6, 8: 4, 9: 2, 10: 1}


def points_for(position: float | int | None) -> int:
    if position is None:
        return 0
    try:
        return POINTS_BY_POSITION.get(int(position), 0)
    except (ValueError, TypeError):
        return 0
