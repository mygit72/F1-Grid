"""Runtime mode helpers.

Deployment mode is OFF by default (local development and the local CLI). It is
turned on by setting the environment variable F1GRID_DEPLOYED to a truthy value
on a hosted deployment. In deployment mode the write actions (publish, score)
are refused, because:

  * a container's filesystem is ephemeral and wiped on redeploy, so a published
    prediction written there would silently vanish and never reach git, and
  * the endpoints are reachable by anyone on the internet.

Publishing and scoring therefore stay a LOCAL CLI + git action only. Everything
read-only (predictions, track record, strategy, scenario, manual grid) keeps
working in deployment mode.
"""
from __future__ import annotations

import os

_TRUTHY = {"1", "true", "yes", "on", "y", "t"}

DEPLOYED_ENV_VAR = "F1GRID_DEPLOYED"

DEPLOYED_REFUSAL = (
    "Publishing and scoring are disabled in deployment mode. A deployed "
    "container's storage is ephemeral (wiped on redeploy) and publicly "
    "reachable, so writes here would be lost and unauthenticated. Publish and "
    "score locally with the CLI (python -m f1grid.publish --next / --score), "
    "which commits to git. All read-only endpoints remain available."
)


def is_deployed() -> bool:
    return os.environ.get(DEPLOYED_ENV_VAR, "").strip().lower() in _TRUTHY
