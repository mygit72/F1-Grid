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


CORS_ENV_VAR = "F1GRID_CORS_ORIGINS"

# Local development origins used when F1GRID_CORS_ORIGINS is not set. A deployment
# sets the env var to exactly the front-end origin(s) it trusts (e.g. the Vercel
# domain) plus localhost. We never use a "*" wildcard: the API is public and a
# wildcard would let any site call it from a browser.
_DEFAULT_CORS_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
    "http://localhost:3000",
)


def cors_allowed_origins() -> list[str]:
    """The exact list of browser origins allowed to call the API. Read from
    F1GRID_CORS_ORIGINS (comma-separated) if set, else the local-dev defaults.
    A literal "*" is rejected so a deploy can never silently open to everyone."""
    raw = os.environ.get(CORS_ENV_VAR, "").strip()
    if not raw:
        return list(_DEFAULT_CORS_ORIGINS)
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    origins = [o for o in origins if o != "*"]
    return origins or list(_DEFAULT_CORS_ORIGINS)
