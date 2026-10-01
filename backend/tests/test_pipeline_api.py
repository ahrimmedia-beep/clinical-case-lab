from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.config import get_settings
from app.db.engine import get_engine
from app.main import create_app
from app.ratelimit import ExtractLimiter, RateLimited, get_limiter
from pipeline.cache import get_extract_cache
from pipeline.providers.base import ProviderUnavailable
from pipeline.providers.fake import SAMPLE_TEXT_FILE, FakeProvider
from pipeline.run import run_pipeline

SAMPLE = SAMPLE_TEXT_FILE.read_text()
KEY = {"X-Internal-Key": "test-key"}

# A port nothing listens on: engine.connect() fails instantly (no DNS, no real Postgres needed).
# These are pure unit tests for the in-memory cache and the rest of the handler; the Postgres
# read-through/write-through is covered against the real test database by
# tests/db/test_extract_cache_db.py. This also exercises the same "DB unreachable -> treat as a
# miss, never fail the request" path production takes if Cloud SQL is briefly unreachable.
UNREACHABLE_DB_URL = "postgresql+asyncpg://caselab:caselab@127.0.0.1:1/caselab"


@pytest.fixture(autouse=True)
def no_local_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty variable beats a value in a developer's local .env file: never call Vertex."""
    for key in ("GCP_PROJECT", "GEMINI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.setenv(key, "")


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("INTERNAL_API_KEY", "test-key")
    monkeypatch.setenv("PIPELINE_FAKE_LLM", "1")
    monkeypatch.setenv("EXTRACT_RATE_PER_MINUTE", "5")
    monkeypatch.delenv("EXTRACT_CACHE_DIR", raising=False)
    get_settings.cache_clear()
    get_limiter.cache_clear()
    get_extract_cache.cache_clear()
    app = create_app()
    app.dependency_overrides[get_engine] = lambda: create_async_engine(
        UNREACHABLE_DB_URL, poolclass=NullPool
    )
    yield TestClient(app)
    get_limiter.cache_clear()
    get_extract_cache.cache_clear()


def post(client: TestClient, headers: dict[str, str] | None = None, **body: Any) -> Any:
    payload = {"text": SAMPLE, "provider": "gemini", **body}
    return client.post("/api/extract", json=payload, headers=headers or KEY)


def test_extract_returns_a_case_with_grounded_spans(client: TestClient) -> None:
    response = post(client)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["case"]["title"] == "Sudden breathlessness after a long flight"
    assert body["grounded_ratio"] == 1.0
    assert "Whitfield" not in body["source_text"]
    span = body["spans"][0]
    assert body["source_text"][span["start"] : span["end"]] == span["quote"]
    assert {"label": "NAME", "count": 2} in body["phi"]


def test_wrong_or_missing_key_is_401(client: TestClient) -> None:
    assert post(client, headers={"X-Internal-Key": "nope"}).status_code == 401
    response = client.post("/api/extract", json={"text": SAMPLE, "provider": "gemini"})
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")


def test_sixth_call_in_a_minute_from_one_ip_is_429(client: TestClient) -> None:
    ip = {**KEY, "X-Forwarded-For": "203.0.113.7"}
    bad_key = {"X-Internal-Key": "nope", "X-Forwarded-For": "203.0.113.7"}
    assert [post(client, headers=bad_key).status_code for _ in range(3)] == [401] * 3
    fresh = [post(client, headers=ip, text=f"{SAMPLE} Note {i}.") for i in range(5)]
    assert [r.status_code for r in fresh] == [200] * 5  # 401s are free
    limited = post(client, headers=ip, text=f"{SAMPLE} Note 6.")
    assert limited.status_code == 429 and "per minute" in limited.json()["detail"]
    other = {**KEY, "X-Forwarded-For": "198.51.100.9, 10.0.0.1"}
    assert post(client, headers=other).status_code == 200


def test_identical_request_is_served_from_the_cache(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    async def counting(text: str, provider: Any, author: Any = None) -> Any:
        calls.append(provider.model)
        return await run_pipeline(text, provider, author)

    monkeypatch.setattr("app.routers.extract.run_pipeline", counting)
    first = post(client)
    second = post(client)
    assert first.status_code == second.status_code == 200
    assert second.json() == first.json()
    assert calls == ["fake-gemini"]
    # the key includes provider and model: the same text on Claude is a new pipeline run
    assert post(client, provider="claude").status_code == 200
    assert calls == ["fake-gemini", "fake-claude"]


def test_cache_hits_do_not_consume_the_rate_budget(client: TestClient) -> None:
    ip = {**KEY, "X-Forwarded-For": "203.0.113.8"}
    assert [post(client, headers=ip).status_code for _ in range(12)] == [200] * 12


def test_failures_are_not_cached(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    providers = iter(
        [FakeProvider(name="gemini", model="fake-gemini", script=["{", "{", "{"])]
        + [FakeProvider.default(name="gemini", model="fake-gemini")]
    )
    monkeypatch.setattr("app.routers.extract.get_provider", lambda *args: next(providers))
    assert post(client).status_code == 502
    assert post(client).status_code == 200


def test_openapi_keeps_the_frozen_extract_contract() -> None:
    operation = create_app().openapi()["paths"]["/api/extract"]["post"]
    assert operation["operationId"] == "extract_case"
    assert set(operation["responses"]) == {"200", "401", "422", "429", "502", "503"}
    assert [p["name"] for p in operation["parameters"]] == ["x-internal-key"]
    committed = json.loads((Path(__file__).parents[1] / "openapi.json").read_text())
    assert operation == committed["paths"]["/api/extract"]["post"]


def test_unknown_model_is_422(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PIPELINE_FAKE_LLM")
    response = post(client, model="gemini-2.5-flash")
    assert response.status_code == 422 and response.json()["title"] == "Unknown model"


def test_missing_credentials_is_503(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PIPELINE_FAKE_LLM")  # autouse fixture already removed every paid key
    response = post(client, provider="claude")
    assert response.status_code == 503
    assert response.json()["title"] == "Model provider unavailable"


def test_quota_exhausted_is_503(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    quota = FakeProvider(
        script=[ProviderUnavailable("429 RESOURCE_EXHAUSTED", retryable=True, status=429)]
    )
    monkeypatch.setattr("app.routers.extract.get_provider", lambda *args: quota)
    assert post(client).status_code == 503


def test_invalid_model_output_three_times_is_502(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    broken = FakeProvider(script=["{", "{", "{"])
    monkeypatch.setattr("app.routers.extract.get_provider", lambda *args: broken)
    response = post(client)
    assert response.status_code == 502
    assert response.json()["detail"] == "the model output failed validation 3 times"


def test_limiter_daily_cap_and_window_reset() -> None:
    now = [1_000_000.0]
    limiter = ExtractLimiter(per_minute=2, daily_cap=3, clock=lambda: now[0])
    limiter.check("a")
    limiter.check("a")
    with pytest.raises(RateLimited, match="per minute"):
        limiter.check("a")
    now[0] += 61
    limiter.check("a")  # window slid
    with pytest.raises(RateLimited, match="daily"):
        limiter.check("b")
    now[0] += 86_400
    limiter.check("b")  # new UTC day
