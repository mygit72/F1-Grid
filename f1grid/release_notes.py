"""Medal-style GitHub Release notes, generated only from published files.

Two blocks live in a release body, each fenced by HTML-comment sentinels:

    <!-- F1GRID:PREDICTION:BEGIN --> ... <!-- F1GRID:PREDICTION:END -->
    <!-- F1GRID:RESULT:BEGIN -->     ... <!-- F1GRID:RESULT:END -->

The PREDICTION block is rendered from the attached, hash-verified prediction JSON
and is written once (at publish). The RESULT block is appended after the race is
graded against the real FastF1 result. Appending a result NEVER rewrites the
prediction block: `append_result_block` copies the prediction bytes verbatim and
asserts they are unchanged. Nothing here is hand-written and no value is invented:
every number comes from the prediction file or the real result.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

PRED_BEGIN = "<!-- F1GRID:PREDICTION:BEGIN -->"
PRED_END = "<!-- F1GRID:PREDICTION:END -->"
RESULT_BEGIN = "<!-- F1GRID:RESULT:BEGIN -->"
RESULT_END = "<!-- F1GRID:RESULT:END -->"

MEDALS = {1: "\U0001F947", 2: "\U0001F948", 3: "\U0001F949"}  # gold, silver, bronze
EXACT = "✅"        # exact position match
SHIFTED = "\U0001F504"  # on the podium, different slot
MISSED = "❌"       # not on the podium


def verify_content_hash(rec: dict) -> bool:
    """Recompute the store's content hash and check it matches the file.

    Mirrors store.predictions.save_prediction: hash the record with content_hash
    and nonce removed, sorted keys, first 10 hex chars of sha256.
    """
    stored = rec.get("content_hash")
    if not stored:
        return False
    tmp = {k: v for k, v in rec.items() if k not in ("content_hash", "nonce", "_path")}
    payload = json.dumps(tmp, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:10] == stored


def _pct(x) -> str:
    return "" if x is None else f"{float(x) * 100:.1f}%"


def _order(rec: dict) -> list[dict]:
    return sorted(rec["prediction"], key=lambda r: r["predicted_position"])


def _prob_columns(rows: list[dict]) -> list[tuple[str, str]]:
    """Only probability columns that actually exist in the file (label, key)."""
    candidates = [("Win", "win_prob"), ("Podium", "podium_prob"),
                  ("Points", "points_prob")]
    present = set().union(*[set(r.keys()) for r in rows]) if rows else set()
    return [(label, key) for label, key in candidates if key in present]


def render_prediction_notes(rec: dict, asset_name: str) -> str:
    """The medal-style prediction block (markdown between the PRED sentinels).

    Renders ONLY fields present in the file. If the file carries a strategy meter
    it is shown; files that predate the meter (e.g. Azerbaijan) simply omit it.
    """
    order = _order(rec)
    prob_cols = _prob_columns(order)
    L: list[str] = []
    L.append(f"# {rec['season']} R{rec['round']} {rec['event']} - predicted")
    L.append("")

    # Podium with medals.
    L.append("## Predicted podium")
    L.append("")
    for row in order[:3]:
        pos = int(row["predicted_position"])
        win = _pct(row.get("win_prob"))
        team = row.get("team")
        team_str = f" ({team})" if team else ""
        win_str = f" - win {win}" if win else ""
        L.append(f"{MEDALS.get(pos, '')} P{pos} - {row['driver']}{team_str}{win_str}")
        L.append("")

    # Predicted top 10 table.
    L.append("## Predicted top 10")
    L.append("")
    header = ["Pos", "Driver", "Team"] + [lbl for lbl, _ in prob_cols]
    L.append("| " + " | ".join(header) + " |")
    L.append("| " + " | ".join("---" for _ in header) + " |")
    for row in order[:10]:
        cells = [str(int(row["predicted_position"])), row["driver"],
                 str(row.get("team") or "")]
        cells += [_pct(row.get(key)) for _, key in prob_cols]
        L.append("| " + " | ".join(cells) + " |")
    L.append("")

    # Optional strategy meter, only if the file has one.
    meter = rec.get("strategy_meter")
    if meter:
        label = meter.get("label", "Strategy")
        level = meter.get("level")
        state = meter.get("state")
        reason = meter.get("reason")
        lvl = f": {level}" if level else (f": {state}" if state else "")
        L.append(f"## {label}{lvl}")
        L.append("")
        if reason:
            L.append(reason)
            L.append("")

    # Verification details.
    L.append("## Verification")
    L.append("")
    L.append(f"- content_hash: `{rec.get('content_hash')}`")
    L.append(f"- made_at_utc: {rec.get('made_at_utc')}")
    L.append(f"- race_start_utc: {rec.get('race_start_utc')}")
    L.append(f"- attached file: `{asset_name}`")
    L.append("- How to verify: download the attached JSON, remove the "
             "`content_hash` and `nonce` fields, dump the rest with sorted keys, "
             "take the first 10 hex chars of its sha256, and confirm it equals the "
             "content_hash above (see the README \"How to verify\" section).")
    L.append("")
    L.append(f"These notes are rendered from the attached file `{asset_name}`, "
             "which (verified by its hash) is the source of truth. The prediction "
             "section is never edited after the race.")
    return "\n".join(L).strip("\n")


def render_result_section(rec: dict, grade: dict, actual_order: list[dict],
                          now_utc: datetime | None = None) -> str:
    """The RESULT block (markdown between the RESULT sentinels).

    `actual_order` is a list of {driver, finish, team} for the real classified
    result, sorted by finishing position. `grade` is the scorer's row.
    """
    now = (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
    ts = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    pred = _order(rec)
    pred_by_pos = {int(r["predicted_position"]): r for r in pred}
    actual_sorted = sorted(actual_order, key=lambda r: r["finish"])
    actual_by_pos = {int(r["finish"]): r for r in actual_sorted}
    actual_podium_drivers = {actual_by_pos[p]["driver"] for p in (1, 2, 3)
                             if p in actual_by_pos}

    L: list[str] = []
    L.append(f"## Result (added after the race, {ts})")
    L.append("")
    L.append("### Predicted podium vs actual")
    L.append("")
    L.append("| Slot | Predicted | Actual | Outcome |")
    L.append("| --- | --- | --- | --- |")
    for pos in (1, 2, 3):
        pr = pred_by_pos.get(pos)
        ac = actual_by_pos.get(pos)
        pr_str = f"{pr['driver']} ({pr.get('team') or ''})" if pr else "-"
        ac_str = f"{ac['driver']} ({ac.get('team') or ''})" if ac else "-"
        marker = ""
        if pr:
            if ac and pr["driver"] == ac["driver"]:
                marker = EXACT
            elif pr["driver"] in actual_podium_drivers:
                marker = SHIFTED
            else:
                marker = MISSED
        L.append(f"| {MEDALS[pos]} P{pos} | {pr_str} | {ac_str} | {marker} |")
    L.append("")
    L.append(f"Legend: {EXACT} exact position, {SHIFTED} made the podium in a "
             f"different slot, {MISSED} missed the podium.")
    L.append("")

    # Predicted vs actual top 10.
    L.append("### Predicted vs actual top 10")
    L.append("")
    L.append("| Pos | Predicted | Actual |")
    L.append("| --- | --- | --- |")
    for pos in range(1, 11):
        pr = pred_by_pos.get(pos)
        ac = actual_by_pos.get(pos)
        L.append(f"| {pos} | {pr['driver'] if pr else '-'} | "
                 f"{ac['driver'] if ac else '-'} |")
    L.append("")

    # Grade metrics.
    beat = grade.get("beat_baseline")
    beat_str = "YES" if beat in (1, 1.0, True) else "NO"
    top1_str = "hit" if grade.get("top1_acc") in (1, 1.0, True) else "miss"
    podium_hits = int(round(float(grade.get("podium_acc", 0.0)) * 3))
    L.append("### Grade")
    L.append("")
    L.append(f"- Spearman (predicted vs actual order): {grade.get('spearman')}")
    L.append(f"- Winner (top 1): {top1_str}")
    L.append(f"- Podium hits: {podium_hits}/3")
    L.append(f"- Mean absolute position error: {grade.get('mae_pos')}")
    L.append(f"- Baseline used: {grade.get('baseline_used')} "
             f"(Spearman {grade.get('baseline_spearman')})")
    L.append(f"- Beat baseline: {beat_str}")
    return "\n".join(L).strip("\n")


def compose_body(rec: dict, asset_name: str, result_section: str | None = None) -> str:
    """Assemble a full release body: prediction block, then optional result block."""
    pred = render_prediction_notes(rec, asset_name)
    body = f"{PRED_BEGIN}\n{pred}\n{PRED_END}\n"
    if result_section:
        body += f"\n{RESULT_BEGIN}\n{result_section}\n{RESULT_END}\n"
    return body


def extract_prediction_block(body: str) -> str | None:
    """Return the text strictly between the PRED sentinels, or None if absent."""
    if PRED_BEGIN not in body or PRED_END not in body:
        return None
    start = body.index(PRED_BEGIN) + len(PRED_BEGIN)
    end = body.index(PRED_END)
    return body[start:end]


def append_result_block(existing_body: str, result_section: str) -> str:
    """Append (or replace) the RESULT block while keeping the PREDICTION block
    byte-for-byte identical. Verifies the invariant in code before returning."""
    if PRED_END not in existing_body:
        raise ValueError("existing body has no prediction block to preserve")
    head = existing_body[: existing_body.index(PRED_END) + len(PRED_END)]
    new_body = f"{head}\n\n{RESULT_BEGIN}\n{result_section}\n{RESULT_END}\n"

    before = extract_prediction_block(existing_body)
    after = extract_prediction_block(new_body)
    if before != after:
        raise AssertionError("prediction block changed while appending result")
    return new_body


# --- GitHub release body read/write (never touches the tag or the asset) -------

def _gh(args: list[str], gh: str | None = None) -> subprocess.CompletedProcess:
    from f1grid.provenance import find_gh
    return subprocess.run([find_gh(gh), *args], capture_output=True, text=True)


def get_release_body(repo: str, tag: str, gh: str | None = None) -> str:
    res = _gh(["release", "view", tag, "--repo", repo, "--json", "body"], gh)
    if res.returncode != 0:
        raise RuntimeError(f"gh release view failed: {(res.stderr or res.stdout).strip()}")
    return json.loads(res.stdout).get("body") or ""


def set_release_body(repo: str, tag: str, body: str, gh: str | None = None) -> None:
    """Edit ONLY the release description (notes). Does not touch the tag, the
    target commit, or any attached asset. Uses --notes-file to avoid arg-length
    and escaping issues with large markdown bodies."""
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False,
                                     encoding="utf-8") as f:
        f.write(body)
        notes_file = f.name
    try:
        res = _gh(["release", "edit", tag, "--repo", repo,
                   "--notes-file", notes_file], gh)
        if res.returncode != 0:
            raise RuntimeError(
                f"gh release edit failed: {(res.stderr or res.stdout).strip()}")
    finally:
        Path(notes_file).unlink(missing_ok=True)


def set_prediction_notes_on_release(repo: str, rec: dict, asset_name: str,
                                    gh: str | None = None,
                                    dry_run: bool = False) -> str:
    """Render the medal prediction notes and set them as the release body."""
    from f1grid.provenance import release_tag
    if not verify_content_hash(rec):
        raise ValueError(
            f"content_hash does not verify for {rec.get('_path') or rec.get('event')}; "
            "refusing to render notes from an unverified file")
    body = compose_body(rec, asset_name)
    if not dry_run:
        set_release_body(repo, release_tag(rec), body, gh)
    return body


def add_result_section_to_release(repo: str, rec: dict, grade: dict,
                                  actual_order: list[dict], gh: str | None = None,
                                  dry_run: bool = False,
                                  now_utc: datetime | None = None) -> str:
    """Append the result section to a race's release, preserving the prediction
    block byte-for-byte. Reads the current body from GitHub first."""
    from f1grid.provenance import release_tag
    tag = release_tag(rec)
    existing = get_release_body(repo, tag, gh)
    result = render_result_section(rec, grade, actual_order, now_utc)
    new_body = append_result_block(existing, result)
    if not dry_run:
        set_release_body(repo, tag, new_body, gh)
    return new_body
