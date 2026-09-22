"""Third-party, server-side proof that a prediction predates its race.

A git commit's committer date is set by the local machine and can be forged, so
it is NOT proof. Proof has to come from timestamps that a third party controls.
For every published prediction we collect, after it is pushed to GitHub:

  1. a GitHub Release (tag `pred-<season>-R<round>`) with the prediction file
     attached and its content hash in the notes  -> GitHub records created_at and
     published_at server-side,
  2. a Wayback Machine snapshot of the raw prediction-file URL  -> archive.org
     records the snapshot timestamp server-side,
  3. the repo's PushEvent created_at from the GitHub events API  -> a supporting,
     short-lived server record of when the push happened.

Each proof is stored in a sidecar JSON under artifacts/provenance/ keyed by the
prediction filename. The immutable prediction file itself is NEVER modified.
Nothing here fabricates a value: if a step fails, the error is recorded verbatim
and reported, never smoothed over.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from f1grid.config import PROV_DIR

WINDOWS_GH = r"C:\Program Files\GitHub CLI\gh.exe"


def find_gh(explicit: str | None = None) -> str:
    """Locate the gh executable (PATH, then the default Windows install)."""
    if explicit:
        return explicit
    onpath = shutil.which("gh")
    if onpath:
        return onpath
    if Path(WINDOWS_GH).exists():
        return WINDOWS_GH
    raise FileNotFoundError(
        "GitHub CLI (gh) not found on PATH or at the default Windows location. "
        "Install it and authenticate before collecting release provenance.")


def _gh(args: list[str], gh: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([find_gh(gh), *args], capture_output=True, text=True)


def release_tag(rec: dict) -> str:
    return f"pred-{rec['season']}-R{int(rec['round']):02d}"


def raw_file_url(repo: str, pred_path: Path, branch: str = "main") -> str:
    name = Path(pred_path).name
    return (f"https://raw.githubusercontent.com/{repo}/{branch}/"
            f"artifacts/predictions/{name}")


def create_github_release(repo: str, rec: dict, pred_path: Path,
                          gh: str | None = None) -> dict:
    """Create (or reuse) a GitHub Release with the prediction attached.

    Returns the release tag plus GitHub's server-side created_at/published_at and
    the browser URL. Raises RuntimeError with gh's stderr if creation fails for a
    reason other than the tag already existing.
    """
    tag = release_tag(rec)
    title = f"Prediction {rec['season']} R{rec['round']} {rec['event']}"
    notes = (
        f"Pre-race prediction for {rec['season']} R{rec['round']} {rec['event']}.\n\n"
        f"- content_hash: {rec.get('content_hash')}\n"
        f"- made_at_utc: {rec.get('made_at_utc')}\n"
        f"- race_start_utc: {rec.get('race_start_utc')}\n\n"
        f"This release exists so GitHub records a server-side timestamp "
        f"(created_at/published_at) proving the prediction file existed before "
        f"the race. The attached JSON is byte-for-byte the published file; verify "
        f"its content_hash as described in the README."
    )
    res = _gh(["release", "create", tag, str(pred_path),
               "--repo", repo, "--title", title, "--notes", notes], gh)
    if res.returncode != 0 and "already exists" not in (res.stderr + res.stdout):
        raise RuntimeError(f"gh release create failed: {(res.stderr or res.stdout).strip()}")

    view = _gh(["release", "view", tag, "--repo", repo,
                "--json", "createdAt,publishedAt,url,tagName"], gh)
    if view.returncode != 0:
        raise RuntimeError(f"gh release view failed: {(view.stderr or view.stdout).strip()}")
    data = json.loads(view.stdout)
    return {
        "tag": data.get("tagName", tag),
        "url": data.get("url"),
        "created_at": data.get("createdAt"),
        "published_at": data.get("publishedAt"),
    }


def push_event_created_at(repo: str, gh: str | None = None) -> str | None:
    """The most recent PushEvent created_at from the repo events API (or None)."""
    res = _gh(["api", f"repos/{repo}/events",
               "--jq", '[.[] | select(.type=="PushEvent")][0].created_at'], gh)
    if res.returncode != 0:
        return None
    val = res.stdout.strip()
    return val or None


def _ts_from_snapshot(snapshot: str) -> str | None:
    m = re.search(r"/web/(\d{14})/", snapshot)
    if not m:
        return None
    d = m.group(1)
    return f"{d[0:4]}-{d[4:6]}-{d[6:8]}T{d[8:10]}:{d[10:12]}:{d[12:14]}Z"


def _curl_json(url: str, timeout: int) -> dict | None:
    """GET a URL with curl (uses the system trust store, so it works behind TLS
    interception where Python's urllib does not) and parse JSON. None on failure."""
    curl = shutil.which("curl")
    if not curl:
        return None
    res = subprocess.run([curl, "-s", "-m", str(timeout), url],
                         capture_output=True, text=True)
    if res.returncode != 0 or not res.stdout.strip():
        return None
    try:
        return json.loads(res.stdout)
    except json.JSONDecodeError:
        return None


def _curl_trigger(url: str, timeout: int) -> None:
    curl = shutil.which("curl")
    if not curl:
        return
    # Best-effort: the anonymous save endpoint may return 500 yet still archive;
    # confirmation comes from the availability API, not this response.
    subprocess.run([curl, "-sL", "-m", str(timeout), "-o", "/dev/null",
                    "https://web.archive.org/save/" + url],
                   capture_output=True, text=True)


def wayback_save(url: str, timeout: int = 150) -> dict:
    """Ask the Wayback Machine to snapshot `url`; return snapshot URL + timestamp.

    Triggers Save Page Now, then CONFIRMS the snapshot via the availability API
    (the anonymous save endpoint frequently returns 500 while still archiving).
    Uses curl so it works behind TLS interception. Raises RuntimeError with the
    exact error if no snapshot can be confirmed; never invents one.
    """
    _curl_trigger(url, timeout)
    avail = _curl_json(
        "https://archive.org/wayback/available?url=" + url, min(timeout, 60))
    if avail is None:
        # Fall back to a direct urllib attempt so the failure text is concrete.
        try:
            req = Request("https://archive.org/wayback/available?url=" + url,
                          headers={"User-Agent": "f1grid-provenance/1.0"})
            with urlopen(req, timeout=timeout) as resp:
                avail = json.loads(resp.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as e:
            raise RuntimeError(f"Wayback availability check failed: {e}") from e
    snap = (avail or {}).get("archived_snapshots", {}).get("closest")
    if not snap or not snap.get("available"):
        raise RuntimeError(
            f"Wayback save produced no confirmed snapshot for {url} "
            f"(availability response: {avail})")
    snapshot = snap["url"]
    return {"snapshot_url": snapshot,
            "timestamp": snap.get("timestamp") and _ts_from_snapshot(snapshot),
            "raw_timestamp": snap.get("timestamp")}


def sidecar_path(pred_path: Path, prov_dir: Path = PROV_DIR) -> Path:
    return prov_dir / (Path(pred_path).name + ".provenance.json")


def write_provenance(pred_path: Path, data: dict,
                     prov_dir: Path = PROV_DIR) -> Path:
    prov_dir.mkdir(parents=True, exist_ok=True)
    p = sidecar_path(pred_path, prov_dir)
    p.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    return p


def read_provenance(pred_path: Path, prov_dir: Path = PROV_DIR) -> dict | None:
    p = sidecar_path(pred_path, prov_dir)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def collect_provenance(repo: str, pred_path: Path, rec: dict, commit_sha: str,
                       *, branch: str = "main", gh: str | None = None,
                       do_wayback: bool = True,
                       prov_dir: Path = PROV_DIR) -> dict:
    """Collect all three proofs and write the sidecar. Each proof is independent:
    a failure in one is recorded as an error string, not fatal to the others."""
    data: dict = {
        "prediction_file": Path(pred_path).name,
        "content_hash": rec.get("content_hash"),
        "race_start_utc": rec.get("race_start_utc"),
        "made_at_utc": rec.get("made_at_utc"),
        "commit_sha": commit_sha,
        "repo": repo,
        "raw_url": raw_file_url(repo, pred_path, branch),
    }
    try:
        data["release"] = create_github_release(repo, rec, pred_path, gh)
    except Exception as e:  # noqa: BLE001 - record, do not fake
        data["release_error"] = str(e)
    try:
        data["push_event_created_at"] = push_event_created_at(repo, gh)
    except Exception as e:  # noqa: BLE001
        data["push_event_error"] = str(e)
    if do_wayback:
        try:
            data["wayback"] = wayback_save(data["raw_url"])
        except Exception as e:  # noqa: BLE001
            data["wayback_error"] = str(e)
    write_provenance(pred_path, data, prov_dir)
    return data
