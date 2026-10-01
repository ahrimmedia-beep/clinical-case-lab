from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.db.engine import get_engine, make_engine
from app.main import create_app


def test_oversized_case_is_413_problem_json() -> None:
    client = TestClient(create_app())  # no lifespan: the 413 fires before any DB access
    response = client.post("/api/cases", json={"title": "x" * 300_000})
    assert response.status_code == 413
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["title"] == "Payload too large"


def test_readyz_is_503_when_database_is_down() -> None:
    app = create_app()
    dead = make_engine("postgresql+asyncpg://nobody:nothing@127.0.0.1:1/none")
    app.dependency_overrides[get_engine] = lambda: dead
    client = TestClient(app)
    response = client.get("/readyz")
    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["title"] == "Database unavailable"
    assert client.get("/healthz").status_code == 200


def test_malformed_requests_get_422_without_touching_the_database() -> None:
    # No lifespan and no database: handlers open connections only after validation passed.
    client = TestClient(create_app())
    bad_attempt = client.post("/api/cases/some-case/attempts", json={"confidence": 9})
    assert bad_attempt.status_code == 422
    bad_reveal = client.post("/api/cases/some-case/reveal", json={"stage": "results"})
    assert bad_reveal.status_code == 422


def test_ingest_requires_the_internal_key_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REQUIRE_INGEST_KEY", "true")
    monkeypatch.setenv("INTERNAL_API_KEY", "s3cret")
    get_settings.cache_clear()
    client = TestClient(create_app())  # no database: the 401 fires before any DB access
    for headers in ({}, {"X-Internal-Key": "wrong"}):
        response = client.post("/api/cases", json={"title": "x"}, headers=headers)
        assert response.status_code == 401
        assert response.headers["content-type"].startswith("application/problem+json")
    # The right key passes the guard; the (invalid) body then fails validation.
    response = client.post("/api/cases", json={"title": "x"}, headers={"X-Internal-Key": "s3cret"})
    assert response.status_code == 422


def test_ingest_is_open_when_the_guard_is_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERNAL_API_KEY", "s3cret")
    get_settings.cache_clear()
    response = TestClient(create_app()).post("/api/cases", json={"title": "x"})
    assert response.status_code == 422  # validation, not 401
