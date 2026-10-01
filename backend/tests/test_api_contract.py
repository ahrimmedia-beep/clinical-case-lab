from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

EXPECTED_OPERATIONS = {
    "healthz",
    "readyz",
    "create_case",
    "list_cases",
    "get_case",
    "reveal_options",
    "create_attempt",
    "extract_case",
    "get_case_review",
    "approve_case",
    "get_case_insights",
    "create_ai_attempt",
}


def operation_ids(spec: dict[str, Any]) -> set[str]:
    return {op["operationId"] for path in spec["paths"].values() for op in path.values()}


def test_openapi_has_every_operation_and_no_split_schemas() -> None:
    spec = create_app().openapi()
    assert operation_ids(spec) == EXPECTED_OPERATIONS
    names = set(spec["components"]["schemas"])
    assert "ClinicalCase" in names
    assert not any(n.endswith("-Input") or n.endswith("-Output") for n in names)


def test_healthz_is_ok() -> None:
    client = TestClient(create_app())
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_validation_errors_are_problem_json() -> None:
    client = TestClient(create_app())
    response = client.post("/api/cases", json={"title": "x"})
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["status"] == 422 and body["title"] == "Validation failed"
    assert isinstance(body["errors"], list) and body["errors"]


def test_internal_endpoints_require_the_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERNAL_API_KEY", "secret")
    client = TestClient(create_app())
    for method, url in [
        ("get", "/api/cases/demo-case/review"),
        ("post", "/api/cases/demo-case/approve"),
        ("get", "/api/cases/demo-case/insights"),
    ]:
        response = getattr(client, method)(url)
        assert response.status_code == 401, url
        assert response.headers["content-type"].startswith("application/problem+json")
    ok = client.get("/api/cases/demo-case/insights", headers={"X-Internal-Key": "secret"})
    assert ok.status_code != 401  # the key passes the guard; the handler is tested in tests/db


def test_ingest_key_is_enforced_only_when_configured(
    monkeypatch: pytest.MonkeyPatch, case_pe: dict[str, Any]
) -> None:
    monkeypatch.setenv("INTERNAL_API_KEY", "secret")
    monkeypatch.setenv("REQUIRE_INGEST_KEY", "true")
    response = TestClient(create_app()).post("/api/cases", json=case_pe)
    assert response.status_code == 401
