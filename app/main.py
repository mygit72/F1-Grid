"""F1Grid - Streamlit app.

Run locally:
    streamlit run app/main.py

Deploy: push this repo to GitHub, then on share.streamlit.io point at
`app/main.py` as the entrypoint. See README.md "Deployment" section.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.theme import THEME_CSS  # noqa: E402
from app.data_loader import (  # noqa: E402
    load_results_cached, build_features_cached, load_or_train_pipeline,
    load_model_card_text, build_scenario, available_races, load_laps_cached,
)
from f1grid import schema as S  # noqa: E402
from f1grid.config import CONFIG  # noqa: E402
from f1grid.runtime import is_deployed, DEPLOYED_REFUSAL  # noqa: E402
from f1grid.model import strategy_meter as _meter  # noqa: E402
from f1grid.model.montecarlo import monte_carlo_outcomes  # noqa: E402
from f1grid.model.strategy_sim import compare_strategies, StintPlan  # noqa: E402
from f1grid.model.tyres import DEFAULT_COMPOUNDS  # noqa: E402
from f1grid.store.predictions import save_prediction, RetroactivePredictionError  # noqa: E402
from f1grid.score.scorer import track_record, SCORECARD  # noqa: E402

st.set_page_config(page_title="F1Grid", page_icon="🏁", layout="wide")
st.markdown(THEME_CSS, unsafe_allow_html=True)


# ── data bootstrap ───────────────────────────────────────────────────────────
results, is_real = load_results_cached()
feats = build_features_cached(results)
pipe, used_saved = load_or_train_pipeline(len(results), feats, CONFIG.eval_seasons)
races = available_races(feats)

st.markdown(
    "<div class='section-eyebrow'>F1GRID</div>"
    "<h1 style='margin-top:0;'>Race weekend prediction, honestly evaluated</h1>",
    unsafe_allow_html=True,
)

if not is_real:
    st.warning(
        "⚠️ Running on **synthetic demo data** - no real FastF1 cache found on this "
        "deployment. Every number below is real *math* on fake *results*. Run "
        "`python -m f1grid.data.ingest` locally and redeploy with the cached "
        "parquet to see real predictions. See the About tab for details.",
        icon="⚠️",
    )

tabs = st.tabs([
    "🏎️ Race Prediction", "🛞 Tyre Strategy", "⚙️ 2026 Scenario Panel",
    "📊 Track Record", "ℹ️ About / Model Card",
])


# ── Tab 1: Race Prediction ──────────────────────────────────────────────────
with tabs[0]:
    left, right = st.columns([1, 2])
    with left:
        st.markdown("<div class='section-eyebrow'>SELECT RACE</div>", unsafe_allow_html=True)
        season_opts = sorted(races[S.SEASON].unique(), reverse=True)
        season = st.selectbox("Season", season_opts, key="race_season")
        season_races = races[races[S.SEASON] == season]
        event = st.selectbox("Grand Prix", season_races[S.EVENT].tolist(), key="race_event")
        row = season_races[season_races[S.EVENT] == event].iloc[0]
        rnd = int(row[S.ROUND])

        st.markdown("<div class='section-eyebrow' style='margin-top:18px;'>SCENARIO</div>",
                   unsafe_allow_html=True)
        rain = st.slider("Rain probability", 0, 100, 0, step=5,
                         help="Manual scenario input - widens outcome variance and "
                              "shifts probability toward wet-skilled drivers. Not a "
                              "weather forecast.") / 100.0
        use_real_grid = st.checkbox(
            "Use the real grid (isolates race-model quality)", value=False,
            help="Off = full forecast using the predicted grid from the quali model "
                 "(what you'd actually publish before qualifying). On = race model "
                 "only, given the real grid, for comparison.",
        )

    race_feats = feats[(feats[S.SEASON] == season) & (feats[S.ROUND] == rnd)].copy()

    if race_feats.empty:
        st.info("No feature rows for this race yet.")
    else:
        order = pipe.predict_weekend(race_feats, use_real_grid=use_real_grid)
        order["wet_skill"] = order.get("wet_skill", 0.5)
        mc = monte_carlo_outcomes(order, rain_prob=rain, n_sims=3000)
        merged = order.merge(
            mc[[S.DRIVER, "win_prob", "podium_prob", "points_prob", "dnf_prob"]],
            on=S.DRIVER,
        ).sort_values("predicted_position")

        with right:
            st.markdown(
                f"<div class='section-eyebrow'>PREDICTED ORDER - {event} "
                f"{'(real grid)' if use_real_grid else '(predicted grid)'}</div>",
                unsafe_allow_html=True,
            )
            max_win = max(merged["win_prob"].max(), 0.01)
            cards = []
            for _, r in merged.head(10).iterrows():
                bar_w = int(100 * r["win_prob"] / max_win)
                cards.append(
                    f"<div class='pos-card'>"
                    f"<div class='pos-num'>{int(r['predicted_position']):02d}</div>"
                    f"<div class='drv-code'>{r[S.DRIVER]}</div>"
                    f"<div class='team-name'>{r.get(S.TEAM,'')}</div>"
                    f"<div class='conf-bar-wrap'><div class='conf-bar' "
                    f"style='width:{bar_w}%'></div></div>"
                    f"<div class='prob'>{r['win_prob']*100:.1f}%</div>"
                    f"</div>"
                )
            st.markdown("".join(cards), unsafe_allow_html=True)

            # ── Strategy meter (item 2): a circuit descriptor shown ALONGSIDE
            # the prediction, never fed into it. Held-out validation did not
            # support a confidence claim, so it is labelled "Strategy complexity".
            if is_real:
                m = _meter.classify_from_artifact(results, load_laps_cached(),
                                                  event, season, rnd)
                if m["state"] == "no_history":
                    badge = "NO HISTORY"
                    detail = m["reason"]
                else:
                    badge = f"{m['label'].upper()}: {m['level']}"
                    detail = m["reason"]
                # Descriptive only: no confidence wording anywhere unless the
                # validated label_mode earned it.
                st.markdown(
                    f"<div class='section-eyebrow' style='margin-top:14px;'>"
                    f"{badge}</div>"
                    f"<div style='opacity:0.8;font-size:0.85rem;'>{detail}</div>",
                    unsafe_allow_html=True,
                )

        st.markdown("<br>", unsafe_allow_html=True)
        c1, c2, c3, c4 = st.columns(4)
        winner = merged.iloc[0]
        for col, label, val in zip(
            (c1, c2, c3, c4),
            ("PREDICTED WINNER", "WIN PROB", "RAIN SCENARIO", "MODE"),
            (f"{winner[S.DRIVER]}", f"{winner['win_prob']*100:.1f}%",
             f"{rain*100:.0f}%", "Real grid" if use_real_grid else "Forecast"),
        ):
            col.markdown(
                f"<div class='metric-box'><div class='val'>{val}</div>"
                f"<div class='lbl'>{label}</div></div>", unsafe_allow_html=True,
            )

        with st.expander("Full predicted field + probabilities"):
            show_cols = [S.DRIVER, S.TEAM, "predicted_position", "win_prob",
                        "podium_prob", "points_prob", "dnf_prob"]
            show_cols = [c for c in show_cols if c in merged.columns]
            st.dataframe(
                merged[show_cols].rename(columns={
                    "predicted_position": "Pred. Pos", "win_prob": "Win %",
                    "podium_prob": "Podium %", "points_prob": "Points %",
                    "dnf_prob": "DNF %",
                }),
                width="stretch", hide_index=True,
            )

        st.markdown("---")
        cpub1, cpub2 = st.columns([3, 1])
        cpub1.caption(
            "Publishing writes this exact prediction to an immutable, "
            "UTC-timestamped file, but ONLY if the race has not started yet - "
            "that pre-race timestamp is what makes the track record verifiable. "
            "A race that has already run is refused from the public record "
            "(use the publish CLI for the next upcoming race)."
        )
        if is_deployed():
            # Deployment mode: writes go to ephemeral, publicly reachable
            # container storage, so publishing is disabled here. It stays a local
            # CLI + git action. Everything read-only above still works.
            cpub2.button("📌 Publish this prediction", width="stretch",
                         disabled=True, help=DEPLOYED_REFUSAL)
            cpub2.caption("Publishing is disabled in deployment mode.")
        elif cpub2.button("📌 Publish this prediction", width="stretch"):
            try:
                meter = _meter.classify_from_artifact(
                    results, load_laps_cached(), event, season, rnd)
                path = save_prediction(
                    season, rnd, event, merged, data_cutoff=f"as of {season} R{rnd-1}",
                    rain_prob=rain, model_meta={"backend": pipe.race.backend,
                                                "used_saved_models": used_saved},
                    strategy_meter=meter,
                )
                st.success(f"Published (verified pre-race): `{Path(path).name}`")
            except RetroactivePredictionError as e:
                st.error(f"Refused: {e}")


# ── Tab 2: Tyre Strategy ────────────────────────────────────────────────────
with tabs[1]:
    st.markdown(
        "<div class='section-eyebrow'>CLEAN-AIR LAP-BY-LAP STRATEGY SIMULATOR</div>",
        unsafe_allow_html=True,
    )
    st.caption(
        "Choose a compound sequence per strategy - pit stops are **not** an input, "
        "they emerge from when each compound's tyre life runs out. This models fuel "
        "burn, per-compound degradation, and a 'cliff' once a tyre is run too long, "
        "plus stochastic safety cars via Monte Carlo. It does **not** model "
        "wheel-to-wheel traffic or overtaking difficulty - see About tab."
    )

    sc1, sc2, sc3 = st.columns(3)
    base_lap = sc1.number_input("Base lap time (s)", 70.0, 120.0, 90.0, step=0.5)
    total_laps = sc2.number_input("Race laps", 40, 78, 57, step=1)
    sc_lambda = sc3.slider("Expected safety cars per race", 0.0, 2.0, 0.6, step=0.1)
    strat_rain = st.slider("Rain probability (strategy sim)", 0, 100, 0, step=5,
                          key="strat_rain") / 100.0

    st.markdown("##### Build strategies to compare")
    compound_names = list(DEFAULT_COMPOUNDS.keys())
    n_strats = st.number_input("Number of strategies to compare", 2, 5, 3)

    candidates = {}
    cols = st.columns(int(n_strats))
    for i in range(int(n_strats)):
        with cols[i]:
            st.markdown(f"**Strategy {i+1}**")
            n_stints = st.number_input(f"Stints", 1, 4, 2 if i else 3, key=f"nstints_{i}")
            seq = []
            for j in range(int(n_stints)):
                default_c = compound_names[min(j, len(compound_names) - 1)]
                comp = st.selectbox(f"Stint {j+1} compound", compound_names,
                                   index=compound_names.index(default_c), key=f"comp_{i}_{j}")
                laps = st.number_input(f"Stint {j+1} laps", 1, 60,
                                      int(total_laps // n_stints), key=f"laps_{i}_{j}")
                seq.append(StintPlan(comp, int(laps)))
            candidates[f"Strategy {i+1}: " + "-".join(s.compound[:1] for s in seq)] = seq

    if st.button("Compare strategies", type="primary"):
        res = compare_strategies(
            base_lap, int(total_laps), candidates, rain_prob=strat_rain,
            n_sims=400, sc_lambda=sc_lambda,
        )
        st.markdown("##### Results (ranked by mean total race time, clean air)")
        for r in res:
            st.markdown(
                f"<div class='pos-card'>"
                f"<div class='drv-code' style='width:auto;margin-right:14px;'>{r['label']}</div>"
                f"<div class='team-name'>{' → '.join(r['sequence'])} · "
                f"{r['n_stops']} stop(s) (emergent)</div>"
                f"<div class='prob' style='width:auto;'>+{r['gap_to_best']}s</div>"
                f"</div>",
                unsafe_allow_html=True,
            )
        st.caption(
            f"Mean times computed over 400 Monte Carlo runs with random safety-car "
            f"timing (λ={sc_lambda}/race). Gaps reflect clean-air pace only."
        )


# ── Tab 3: 2026 Scenario Panel ──────────────────────────────────────────────
with tabs[2]:
    st.markdown("<div class='section-eyebrow'>2026 TEAM & DRIVER OVERRIDES</div>",
               unsafe_allow_html=True)
    st.caption(
        "Every dial below defaults to a value computed from real historical "
        "results "
        "<span class='assumption-tag tag-real'>data-derived</span>. Aero and power "
        "unit aren't observable from finishing positions alone, so they default "
        "neutral and any change you make is an explicit "
        "<span class='assumption-tag tag-assumed'>your assumption</span> override - "
        "never silently folded into the trained model.",
        unsafe_allow_html=True,
    )

    # build_scenario is @st.cache_resource: a SHARED object across every session
    # and rerun. Mutating it with set_team/set_driver would leak one user's
    # overrides into everyone else's panel (and into the API's defaults source).
    # Keep the shared object read-only and mutate only a per-session copy.
    scenario_defaults = build_scenario(len(results), results)
    if "scenario_overrides" not in st.session_state:
        st.session_state["scenario_overrides"] = scenario_defaults.copy()
    scenario = st.session_state["scenario_overrides"]

    pcol1, pcol2 = st.columns(2)
    with pcol1:
        st.markdown("##### Team dials")
        team = st.selectbox("Team", sorted(scenario.teams.keys()))
        td = scenario.teams[team]
        car_pace = st.slider("Car pace  🟢 data-derived", 0.0, 1.0, td.car_pace, 0.01)
        reliability = st.slider("Reliability  🟢 data-derived", 0.0, 1.0, td.reliability, 0.01)
        aero = st.slider("Aero efficiency  🟡 assumption", 0.0, 1.0, td.aero_efficiency, 0.01)
        pu = st.slider("Power unit  🟡 assumption", 0.0, 1.0, td.power_unit, 0.01)
        if st.button("Apply team overrides"):
            scenario.set_team(team, car_pace=car_pace, reliability=reliability,
                             aero_efficiency=aero, power_unit=pu)
            st.success(f"Updated {team}.")

    with pcol2:
        st.markdown("##### Driver dials")
        driver = st.selectbox("Driver", sorted(scenario.drivers.keys()))
        dd = scenario.drivers[driver]
        pace_r = st.slider("Pace rating  🟢 data-derived", 0.0, 1.0, dd.pace_rating, 0.01)
        quali_r = st.slider("Qualifying rating  🟢 data-derived", 0.0, 1.0, dd.quali_rating, 0.01)
        consistency = st.slider("Consistency  🟢 data-derived", 0.0, 1.0, dd.consistency, 0.01)
        wet_skill = st.slider("Wet skill  🟢 data-derived*", 0.0, 1.0, dd.wet_skill, 0.01,
                             help="*Falls back to neutral 0.5 unless wet-race events "
                                  "are tagged for this dataset.")
        reliab_exp = st.slider("Reliability exposure (DNF rate)  🟢 data-derived",
                              0.0, 0.5, dd.reliability_exposure, 0.01)
        if st.button("Apply driver overrides"):
            scenario.set_driver(driver, pace_rating=pace_r, quali_rating=quali_r,
                               consistency=consistency, wet_skill=wet_skill,
                               reliability_exposure=reliab_exp)
            st.success(f"Updated {driver}.")

    st.markdown("---")
    st.markdown("##### Preview: apply this scenario to a race")
    prev_season = st.selectbox("Season", sorted(races[S.SEASON].unique(), reverse=True),
                              key="scenario_season")
    prev_races = races[races[S.SEASON] == prev_season]
    prev_event = st.selectbox("Grand Prix", prev_races[S.EVENT].tolist(), key="scenario_event")
    prow = prev_races[prev_races[S.EVENT] == prev_event].iloc[0]

    if st.button("Run scenario prediction", type="primary"):
        race_feats = feats[(feats[S.SEASON] == prev_season) & (feats[S.ROUND] == int(prow[S.ROUND]))].copy()
        adjusted = scenario.apply_to_features(race_feats)
        scenario_order = pipe.race.predict_order(adjusted)
        st.dataframe(
            scenario_order[[S.DRIVER, S.TEAM, "predicted_position"]]
            .sort_values("predicted_position").rename(columns={"predicted_position": "Scenario Pos"}),
            width="stretch", hide_index=True,
        )


# ── Tab 4: Track Record ─────────────────────────────────────────────────────
with tabs[3]:
    st.markdown("<div class='section-eyebrow'>VERIFIABLE PUBLIC TRACK RECORD</div>",
               unsafe_allow_html=True)
    st.caption(
        "Predictions are timestamped before each race and graded after. This table "
        "only grows from real, pre-committed predictions - nothing here can be "
        "edited after the fact."
    )
    tr = track_record()
    if tr.empty:
        st.info(
            "No graded races yet. Publish a prediction from the Race Prediction "
            "tab, then run `score_race()` after the real result is in (see README) "
            "to populate this table."
        )
    else:
        m1, m2, m3 = st.columns(3)
        for col, label, val in zip(
            (m1, m2, m3),
            ("RACES GRADED", "CUMULATIVE PODIUM ACC.", "BEAT BASELINE RATE"),
            (len(tr), f"{tr['cum_podium'].iloc[-1]*100:.1f}%",
             f"{tr['cum_beat_baseline'].iloc[-1]*100:.1f}%"),
        ):
            col.markdown(
                f"<div class='metric-box'><div class='val'>{val}</div>"
                f"<div class='lbl'>{label}</div></div>", unsafe_allow_html=True,
            )
        st.dataframe(tr, width="stretch", hide_index=True)


# ── Tab 5: About / Model Card ───────────────────────────────────────────────
with tabs[4]:
    st.markdown("<div class='section-eyebrow'>WHY THIS PROJECT IS BUILT THIS WAY</div>",
               unsafe_allow_html=True)
    st.markdown(
        "F1Grid is built around one rule: **a feature describing a race may only "
        "use information available before that race starts.** Every evaluation here "
        "is walk-forward (train on the past, predict the next race, never peek at "
        "the future) and always reported next to a grid-order baseline, so any "
        "claimed improvement is a real, checkable number - not one that's "
        "guaranteed by construction.\n\n"
        "Predictions are written to immutable, timestamped files before the result "
        "is known, so the track record on the previous tab is auditable rather "
        "than just claimed. The 2026 scenario panel keeps real, data-derived "
        "defaults separate from your hand-set assumptions - never blending the two "
        "silently."
    )
    card = load_model_card_text()
    if card:
        st.markdown("---")
        st.markdown(card)
    else:
        st.info(
            "No MODEL_CARD.md found - run `python -m f1grid.train` locally "
            "(after ingesting real data) to generate one with real walk-forward "
            "metrics for this exact model."
        )
    st.markdown("---")
    st.caption(
        "Uses only publicly available FastF1/OpenF1 data. No team logos, sponsor "
        "marks, or official F1 branding. Predictions are analysis and "
        "entertainment, not betting advice, and carry no guarantee of accuracy."
    )
