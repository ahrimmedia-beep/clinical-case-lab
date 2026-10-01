"""Shared-secret guard for endpoints that only the web server and seed scripts call."""

from __future__ import annotations

import secrets

from fastapi import Request

from app.config import get_settings
from app.problems import raise_problem


def require_internal_key(request: Request) -> None:
    """401 unless `X-Internal-Key` matches `INTERNAL_API_KEY`.

    When no key is configured (local compose, tests) the guard is open; production always
    sets the key from Secret Manager.
    """
    settings = get_settings()
    expected = settings.internal_api_key.get_secret_value() if settings.internal_api_key else ""
    supplied = request.headers.get("x-internal-key", "")
    if expected and not secrets.compare_digest(supplied.encode(), expected.encode()):
        raise_problem(401, "Unauthorized", "Missing or wrong X-Internal-Key header.")


def require_ingest_key(request: Request) -> None:
    """Case ingest is open locally and key-protected in production (`REQUIRE_INGEST_KEY=true`)."""
    if get_settings().require_ingest_key:
        require_internal_key(request)
