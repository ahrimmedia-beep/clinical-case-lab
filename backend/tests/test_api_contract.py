from __future__ import annotations

from typing import Any

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
