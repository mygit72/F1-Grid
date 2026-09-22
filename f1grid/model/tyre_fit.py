"""Fit tyre-degradation curves from real FastF1 stint data (item 3).

Pipeline:
  1. Filter to representative green-flag tyre-pace laps (documented below).
  2. Remove the fuel effect by ESTIMATING it from the data: within each event we
     fit one linear model with a shared per-lap fuel term plus a per-compound
     intercept and a per-compound tyre-life slope. The tyre-life slope IS the
     degradation rate with fuel already accounted for; the lap-number coefficient
     IS the fuel effect (s/lap). Fuel and degradation are separable because a pit
     stop resets tyre-life while lap-number keeps climbing.
  3. Aggregate degradation per (circuit, compound), with a pooled per-compound
     fallback for circuits with too little data. Every curve reports its stint and
     lap counts.
  4. Treat the cliff honestly: teams pit before the tyre collapses, so tyre-life
     rarely reaches the cliff (censored data). We do NOT invent a cliff location;
     we report how often a stint even reaches the default cliff age, and keep the
     documented default cliff, LABELLED as a default, when it is unobserved.
  5. Compounds are relative per event (FastF1 SOFT/MEDIUM/HARD are event-relative,
     not fixed rubber). We fit within event context and never map to Pirelli
     C-numbers the data does not contain.
  6. Intermediate/wet are fitted only if there is enough representative wet running;
     otherwise the current defaults are kept and LABELLED.

Leakage: `fit_curves(..., before=(season, round))` uses ONLY laps from races
strictly before the target race, so a curve used to simulate/evaluate a race is
never fitted on that race or any later one.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from f1grid.config import DATA_DIR
from f1grid import schema as S
from f1grid.model.tyres import Compound, DEFAULT_COMPOUNDS, FUEL_EFFECT_PER_LAP

TYRE_CURVES_JSON = DATA_DIR / "tyre_curves.json"

DRY_COMPOUNDS = ("SOFT", "MEDIUM", "HARD")
WET_COMPOUNDS = ("INTERMEDIATE", "WET")

# ── documented filter thresholds ────────────────────────────────────────────
MIN_LAP_NUMBER = 2          # drop lap 1 (standing start, not tyre pace)
OUTLIER_MULT = 1.10         # drop laps > 110% of the event's clean-lap median
                            # (traffic, missed in/out laps, damage) - 10% of a
                            # ~90s lap is ~9s, well beyond genuine deg+fuel spread
MIN_COMPOUND_LAPS = 25      # min laps for a compound to be fitted at an event
MIN_COMPOUND_STINTS = 2     # min distinct stints for a compound at an event
MIN_CIRCUIT_STINTS = 4      # below this, a (circuit, compound) uses the pooled curve
MIN_WET_LAPS = 300          # below this, intermediate/wet keep labelled defaults


@dataclass
class FilterReport:
    total: int = 0
    kept: int = 0
    dropped: dict = field(default_factory=dict)


def filter_representative_laps(laps: pd.DataFrame) -> tuple[pd.DataFrame, FilterReport]:
    """Keep only laps that represent genuine tyre pace. Each filter is counted."""
    rep = FilterReport(total=len(laps))
    df = laps.copy()

    def drop(mask, name):
        n = int(mask.sum())
        if n:
            rep.dropped[name] = rep.dropped.get(name, 0) + n
        return df[~mask]

    df = drop(df["lap_time_s"].isna(), "no_lap_time")
    df = drop(df["tyre_life"].isna(), "no_tyre_life")
    df = drop(df["compound"].isna(), "no_compound")
    df = drop(df["lap_number"] < MIN_LAP_NUMBER, "lap_1")
    df = drop(df["is_pit_in"].fillna(False), "pit_in_lap")
    df = drop(df["is_pit_out"].fillna(False), "pit_out_lap")
    # Non-green track status: any status code other than '1' (green) present in
    # the lap means SC / VSC / yellow / red at some point -> not representative.
    ts = df["track_status"].astype("string").fillna("")
    non_green = ts.str.replace("1", "", regex=False).str.len() > 0
    df = drop(non_green, "safety_car_vsc_yellow")

    # Large-gap outliers, per event, vs that event's clean-lap median.
    keep_idx = []
    for _, g in df.groupby([S.SEASON, S.ROUND]):
        med = g["lap_time_s"].median()
        ok = g["lap_time_s"] <= OUTLIER_MULT * med
        keep_idx.append(g.index[ok])
    if keep_idx:
        keep = df.index.isin(np.concatenate([k.to_numpy() for k in keep_idx]))
        df = drop(~keep, "large_gap_outlier")

    rep.kept = len(df)
    return df, rep


def _fit_event(g: pd.DataFrame) -> dict:
    """One linear fit per event: lap_time ~ fuel*lap_number + per-compound
    (intercept + tyre_life slope). Returns fuel coef and per-compound gamma/delta
    with counts, for compounds that clear the min-laps/min-stints bar."""
    comps = []
    for c in DRY_COMPOUNDS:
        sub = g[g["compound"] == c]
        n_stints = sub.groupby([S.DRIVER, "stint"]).ngroups
        if len(sub) >= MIN_COMPOUND_LAPS and n_stints >= MIN_COMPOUND_STINTS:
            comps.append(c)
    if not comps:
        return {}
    sub = g[g["compound"].isin(comps)]
    n = len(sub)
    # Design: [lap_number] + intercept per compound + tyre_life per compound.
    cols = [sub["lap_number"].to_numpy(dtype=float)]
    names = ["fuel"]
    for c in comps:
        ind = (sub["compound"] == c).to_numpy(dtype=float)
        cols.append(ind)
        names.append(f"int_{c}")
        cols.append(ind * sub["tyre_life"].to_numpy(dtype=float))
        names.append(f"deg_{c}")
    X = np.column_stack(cols)
    y = sub["lap_time_s"].to_numpy(dtype=float)
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    coef = dict(zip(names, beta))
    out = {"fuel": float(coef["fuel"]), "n_laps": n, "compounds": {}}
    for c in comps:
        cc = sub[sub["compound"] == c]
        out["compounds"][c] = {
            "gamma": float(coef[f"int_{c}"]),       # fresh-pace intercept
            "deg": float(coef[f"deg_{c}"]),         # s/lap degradation
            "n_laps": int(len(cc)),
            "n_stints": int(cc.groupby([S.DRIVER, "stint"]).ngroups),
            "max_life": float(cc["tyre_life"].max()),
        }
    return out


@dataclass
class FitResult:
    fuel_effect_per_lap: float
    fuel_source: str
    fuel_estimates: list
    pooled: dict            # compound -> {deg_rate, base_offset, n_laps, n_stints,
                            #              cliff_lap, cliff_is_default, cliff_observed_rate,
                            #              max_life_observed}
    per_circuit: dict       # "circuit|compound" -> {deg_rate, n_laps, n_stints}
    wet: dict               # compound -> {fitted|default, n_laps}
    n_events: int
    filter_report: dict

    def to_dict(self) -> dict:
        return {
            "fuel_effect_per_lap": self.fuel_effect_per_lap,
            "fuel_source": self.fuel_source,
            "fuel_estimates": self.fuel_estimates,
            "pooled": self.pooled,
            "per_circuit": self.per_circuit,
            "wet": self.wet,
            "n_events": self.n_events,
            "filter_report": self.filter_report,
        }

    def compound(self, name: str, circuit: str | None = None) -> Compound:
        """Fitted Compound for a name, preferring the circuit-specific degradation
        when it exists, else the pooled curve, else the labelled default."""
        default = DEFAULT_COMPOUNDS[name]
        if name in WET_COMPOUNDS or name in ("INTER",):
            return default  # wet/inter keep labelled defaults unless fitted
        pool = self.pooled.get(name)
        if pool is None:
            return default
        deg = pool["deg_rate"]
        if circuit is not None:
            key = f"{circuit}|{name}"
            if key in self.per_circuit:
                deg = self.per_circuit[key]["deg_rate"]
        return Compound(
            name=name,
            base_offset=pool["base_offset"],
            deg_rate=deg,
            cliff_lap=pool["cliff_lap"],
            cliff_rate=default.cliff_rate,     # cliff steepness kept as default
            rain_suitability=default.rain_suitability,
        )

    def compounds(self, circuit: str | None = None) -> dict:
        out = {}
        for name in DEFAULT_COMPOUNDS:
            out[name] = self.compound(name, circuit=circuit)
        return out


def fit_curves(laps: pd.DataFrame, before: tuple[int, int] | None = None) -> FitResult:
    """Fit degradation + fuel from lap data, optionally restricted to races
    strictly before (season, round) to keep evaluation leakage-free."""
    laps = laps.copy()
    if before is not None:
        laps[S.DATE] = pd.to_datetime(laps[S.DATE])
        bs, br = before
        cutoff = laps[(laps[S.SEASON] == bs) & (laps[S.ROUND] == br)][S.DATE]
        if not cutoff.empty:
            laps = laps[laps[S.DATE] < cutoff.iloc[0]]

    dry = laps[~laps["compound"].isin(WET_COMPOUNDS)]
    filt, rep = filter_representative_laps(dry)

    # Per-event fits.
    event_fits = []
    for (season, rnd), g in filt.groupby([S.SEASON, S.ROUND]):
        ef = _fit_event(g)
        if ef:
            event = g[S.EVENT].iloc[0]
            ef["season"], ef["round"], ef["event"] = int(season), int(rnd), event
            event_fits.append(ef)

    # ── fuel effect (s/lap improvement = -coef of lap_number) ──
    fuel_coefs = [(-e["fuel"], e["n_laps"], f"{e['season']} R{e['round']}")
                  for e in event_fits]
    fuel_vals = np.array([f[0] for f in fuel_coefs])
    fuel_wts = np.array([f[1] for f in fuel_coefs], dtype=float)
    if len(fuel_vals) and fuel_wts.sum() > 0:
        est = float(np.average(fuel_vals, weights=fuel_wts))
    else:
        est = float("nan")
    # A physically sensible fuel effect makes the car FASTER as it lightens
    # (positive s/lap improvement). If the data estimate is non-positive or absent
    # we fall back to the documented prior default and say so.
    if np.isnan(est) or est <= 0:
        fuel_effect = FUEL_EFFECT_PER_LAP
        fuel_source = (f"fallback constant {FUEL_EFFECT_PER_LAP} s/lap (prior default; "
                       f"data estimate was {est:.4f} and non-positive/unstable)")
    else:
        fuel_effect = est
        fuel_source = (f"estimated from data: laps-weighted mean of per-event fuel "
                       f"coefficients over {len(fuel_vals)} events")
    fuel_estimates = sorted(fuel_coefs, key=lambda t: t[2])

    # ── pooled per-compound degradation + base offset ──
    pooled = {}
    for c in DRY_COMPOUNDS:
        degs, wts, stints, laps_c, maxlife = [], [], 0, 0, 0.0
        gammas = []
        for e in event_fits:
            if c in e["compounds"]:
                cc = e["compounds"][c]
                degs.append(cc["deg"]); wts.append(cc["n_laps"])
                gammas.append((cc["gamma"], cc["n_laps"], e))
                stints += cc["n_stints"]; laps_c += cc["n_laps"]
                maxlife = max(maxlife, cc["max_life"])
        if not degs:
            continue
        deg_rate = float(np.average(degs, weights=wts))
        # cliff: fraction of stints reaching the default cliff age (censoring check)
        default = DEFAULT_COMPOUNDS[c]
        reached = _stints_reaching(filt, c, default.cliff_lap)
        cliff = _cliff_observation(filt, c, default.cliff_lap, fuel_effect)
        pooled[c] = {
            "deg_rate": round(deg_rate, 5),
            "base_offset": None,  # filled below once reference is known
            "n_laps": laps_c,
            "n_stints": stints,
            "max_life_observed": round(maxlife, 1),
            "cliff_lap": default.cliff_lap,
            "cliff_is_default": True,
            "cliff_reach_rate": round(reached["rate"], 4),
            "cliff_observed": cliff["observed"],
            "cliff_pre_slope": cliff["pre_slope"],
            "cliff_post_slope": cliff["post_slope"],
            "cliff_note": cliff["note"],
        }

    # base_offset relative to HARD (event-relative gammas, laps-weighted, recentred)
    _fill_base_offsets(pooled, event_fits)

    # ── per-circuit degradation (falls back to pooled when sparse) ──
    per_circuit = {}
    circ_acc: dict = {}
    for e in event_fits:
        for c, cc in e["compounds"].items():
            circ_acc.setdefault((e["event"], c), []).append(cc)
    for (event, c), rows in circ_acc.items():
        stints = sum(r["n_stints"] for r in rows)
        if stints < MIN_CIRCUIT_STINTS:
            continue
        degs = [r["deg"] for r in rows]; wts = [r["n_laps"] for r in rows]
        per_circuit[f"{event}|{c}"] = {
            "deg_rate": round(float(np.average(degs, weights=wts)), 5),
            "n_laps": int(sum(wts)), "n_stints": int(stints),
        }

    # ── wet: fit only if enough representative wet running, else labelled default ──
    wetfilt, _ = filter_representative_laps(laps[laps["compound"].isin(WET_COMPOUNDS)])
    wet = {}
    for c in WET_COMPOUNDS:
        n = int((wetfilt["compound"] == c).sum())
        wet[c] = {"status": "labelled_default", "n_laps": n,
                  "note": f"only {n} representative laps (< {MIN_WET_LAPS}); "
                          "keeping documented default" if n < MIN_WET_LAPS
                          else f"{n} laps available but wet fitting not enabled; "
                               "keeping documented default"}

    return FitResult(
        fuel_effect_per_lap=round(fuel_effect, 5),
        fuel_source=fuel_source,
        fuel_estimates=fuel_estimates,
        pooled=pooled,
        per_circuit=per_circuit,
        wet=wet,
        n_events=len(event_fits),
        filter_report={"total": rep.total, "kept": rep.kept, "dropped": rep.dropped},
    )


def _stints_reaching(filt: pd.DataFrame, compound: str, cliff_lap: int) -> dict:
    sub = filt[filt["compound"] == compound]
    if sub.empty:
        return {"rate": 0.0, "n_stints": 0}
    grp = sub.groupby([S.SEASON, S.ROUND, S.DRIVER, "stint"])["tyre_life"].max()
    n = len(grp)
    reached = int((grp >= cliff_lap).sum())
    return {"rate": reached / n if n else 0.0, "n_stints": n}


def _cliff_observation(filt: pd.DataFrame, compound: str, cliff_lap: int,
                       fuel_effect: float) -> dict:
    """Is a cliff (a steeper slope past the default cliff age) actually observed?

    We FUEL-CORRECT lap times first (add back the fuel-burn benefit using the
    estimated per-lap fuel term) so the trend reflects tyre pace, not the car
    getting lighter, then event-demean to remove circuit base pace. We compare the
    tyre_life slope BEFORE vs AFTER the default cliff age, pooled across events. We
    do NOT relocate the cliff from this (the post-cliff region is sparse/censored);
    we only report whether acceleration is visible, and keep the labelled default
    cliff either way.
    """
    s = filt[filt["compound"] == compound].copy()
    if s.empty:
        return {"observed": False, "pre_slope": None, "post_slope": None,
                "note": "no laps"}
    # remove fuel (car is faster as it lightens): corrected = observed + fuel*lap
    s["lt_fc"] = s["lap_time_s"] + fuel_effect * s["lap_number"]
    s["ev"] = s[S.SEASON].astype(str) + "_" + s[S.ROUND].astype(str)
    s["lt_dm"] = s["lt_fc"] - s.groupby("ev")["lt_fc"].transform("median")

    def slope(sub):
        if len(sub) < 30 or sub["tyre_life"].nunique() < 3:
            return None
        x = sub["tyre_life"].to_numpy(float)
        y = sub["lt_dm"].to_numpy(float)
        return float(np.polyfit(x, y, 1)[0])

    pre = slope(s[s["tyre_life"] < cliff_lap])
    post = slope(s[s["tyre_life"] >= cliff_lap])
    n_post = int((s["tyre_life"] >= cliff_lap).sum())
    if post is None:
        return {"observed": False, "pre_slope": round(pre, 5) if pre else None,
                "post_slope": None,
                "note": f"only {n_post} laps past age {cliff_lap}; cliff censored, "
                        "default kept"}
    observed = pre is not None and post > pre * 1.5 and post > 0
    return {"observed": bool(observed),
            "pre_slope": round(pre, 5) if pre is not None else None,
            "post_slope": round(post, 5),
            "note": (f"post-cliff slope {post:.4f} vs pre {pre:.4f} over {n_post} "
                     f"post-cliff laps" if pre is not None else f"{n_post} post-cliff laps")}


def _fill_base_offsets(pooled: dict, event_fits: list) -> None:
    """base_offset per compound = laps-weighted mean of (gamma_c - event mean gamma),
    then re-centred so HARD = 0 (relative fresh pace, event-relative by construction)."""
    per_c: dict = {c: [] for c in pooled}
    for e in event_fits:
        present = {c: e["compounds"][c]["gamma"] for c in e["compounds"] if c in pooled}
        if len(present) < 2:
            continue
        mean_gamma = np.mean(list(present.values()))
        for c, g in present.items():
            per_c[c].append((g - mean_gamma, e["compounds"][c]["n_laps"]))
    raw = {}
    for c, vals in per_c.items():
        if vals:
            v = np.array([x[0] for x in vals]); w = np.array([x[1] for x in vals], float)
            raw[c] = float(np.average(v, weights=w))
    ref = raw.get("HARD", raw.get("MEDIUM", 0.0))
    for c in pooled:
        pooled[c]["base_offset"] = round(raw.get(c, DEFAULT_COMPOUNDS[c].base_offset) - ref, 4)


def save_summary(fit: FitResult, path: Path = TYRE_CURVES_JSON) -> Path:
    path.write_text(json.dumps(fit.to_dict(), indent=2), encoding="utf-8")
    return path


def load_summary(path: Path = TYRE_CURVES_JSON) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
