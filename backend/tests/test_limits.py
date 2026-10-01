"""Request limits without a database: per-IP windows, the fallback day budget, the client IP
behind Cloud Run, and the global request-body cap. The Postgres-backed daily extraction budget,
the attempt throttle and the AI-draft cap are covered in tests/db/test_api_limits.py."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.config import get_settings
from app.main import MAX_BODY_BYTES, create_app
from app.ratelimit import DailyBudget, RateLimited, SlidingWindow, client_ip

DAY = 86_400


def test_sliding_window_counts_per_key_and_slides() -> None:
    now = [1_000_000.0]
    window = SlidingWindow(per_minute=2, noun="extractions", clock=lambda: now[0])
    window.check("a")
    window.check("a")
    with pytest.raises(RateLimited, match="At most 2 extractions per minute; retry in 60 s"):
        window.check("a")
    window.check("b")  # another key has its own window
    now[0] += 61
    window.check("a")  # the window slid


def test_fallback_day_budget_resets_at_utc_midnight() -> None:
    now = [DAY * 20_000 + 100.0]
    budget = DailyBudget(cap=2, clock=lambda: now[0])
    budget.take()
    budget.take()
    with pytest.raises(RateLimited, match="daily extraction budget is used up") as refused:
        budget.take()
    assert refused.value.retry_after_s == DAY - 100
    now[0] += DAY
    budget.take()


def request_with(headers: dict[str, str]) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/",
            "query_string": b"",
            "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
            "client": ("192.0.2.1", 50_000),
        }
    )


@pytest.fixture
def keyed(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("INTERNAL_API_KEY", "k3y")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.usefixtures("keyed")
def test_client_ip_is_the_last_forwarded_entry_unless_the_web_server_names_the_user() -> None:
    # Cloud Run's front end appends the peer it saw; everything before it is client-supplied.
    spoofed = "203.0.113.7, 198.51.100.9"
    assert client_ip(request_with({"x-forwarded-for": spoofed})) == "198.51.100.9"
    wrong_key = {"x-forwarded-for": spoofed, "x-internal-key": "nope"}
    assert client_ip(request_with(wrong_key)) == "198.51.100.9"
    # The web server holds the key and forwards the browser's address as the first entry.
    web = {"x-forwarded-for": spoofed, "x-internal-key": "k3y"}
    assert client_ip(request_with(web)) == "203.0.113.7"
    assert client_ip(request_with({"x-forwarded-for": " , "})) == "192.0.2.1"
    assert client_ip(request_with({})) == "192.0.2.1"


def test_client_ip_trusts_the_first_entry_when_no_key_is_configured() -> None:
    # Local compose and tests: no key, so the guard is open and every caller counts as the web.
    assert client_ip(request_with({"x-forwarded-for": "203.0.113.7, 10.0.0.1"})) == "203.0.113.7"


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())  # no lifespan, no database: the cap fires before any route


def test_bodies_over_the_global_cap_are_413_problem_json(client: TestClient) -> None:
    attempt = {"choices": {}, "diagnosis_text": "x" * (MAX_BODY_BYTES + 1), "confidence": 3}
    response = client.post("/api/cases/some-case/attempts", json=attempt)
    assert response.status_code == 413
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["title"] == "Payload too large"
    assert response.json()["detail"] == f"A request body must be at most {MAX_BODY_BYTES} bytes."


def test_a_chunked_body_without_content_length_is_capped_too(client: TestClient) -> None:
    def chunks() -> Iterator[bytes]:
        yield b'{"stage": "workup", "option_keys": ["'
        yield b"A" * (MAX_BODY_BYTES + 1)
        yield b'"]}'

    response = client.post(
        "/api/cases/some-case/reveal",
        content=chunks(),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 413
    assert response.headers["content-type"].startswith("application/problem+json")


def test_extract_fits_20000_four_byte_characters(client: TestClient) -> None:
    # 20,001 emoji are ~80 KB of JSON: past the global cap, so extract has its own higher one.
    # The body reaches validation (422 for one character too many), not the 413.
    response = client.post("/api/extract", json={"text": "\U0001f600" * 20_001})
    assert response.status_code == 422


def test_ingest_keeps_its_own_256_kb_cap(client: TestClient) -> None:
    response = client.post("/api/cases", json={"title": "x" * 100_000})
    assert response.status_code == 422  # past 64 KB, under 256 KB: validation, not 413
    assert client.post("/api/cases", json={"title": "x" * 300_000}).status_code == 413
