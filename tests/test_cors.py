"""CORS is locked to explicit origins, never a wildcard (item 2 / item 4).

The API is public, so a "*" wildcard would let any website call it from a
browser. Origins come from F1GRID_CORS_ORIGINS (comma-separated) or local-dev
defaults, and a literal "*" is always dropped.
"""
from __future__ import annotations

from f1grid import runtime


def test_default_origins_have_no_wildcard(monkeypatch):
    monkeypatch.delenv(runtime.CORS_ENV_VAR, raising=False)
    origins = runtime.cors_allowed_origins()
    assert origins, "expected some default dev origins"
    assert "*" not in origins


def test_env_override_parsed_and_wildcard_dropped(monkeypatch):
    monkeypatch.setenv(runtime.CORS_ENV_VAR, "https://foo.vercel.app, *, http://localhost:5173")
    origins = runtime.cors_allowed_origins()
    assert "https://foo.vercel.app" in origins
    assert "http://localhost:5173" in origins
    assert "*" not in origins


def test_all_star_falls_back_to_defaults(monkeypatch):
    # If someone sets only "*", we must NOT open to everyone: fall back to defaults.
    monkeypatch.setenv(runtime.CORS_ENV_VAR, "*")
    origins = runtime.cors_allowed_origins()
    assert "*" not in origins
    assert origins == list(runtime._DEFAULT_CORS_ORIGINS)


# The live middleware behaviour (allowed origin gets the ACAO header, a disallowed
# origin does not) is exercised end-to-end against the running container by
# scripts/container_api_checks.sh in the docker-test CI job.
