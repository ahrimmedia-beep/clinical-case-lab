"""Limits that live in Postgres or guard the public write paths (fake provider only).

- The extraction daily budget is a row in `daily_usage`, reserved before every paid run, so it
  survives an instance restart (scale to zero) and counts failed runs too.
- POST /api/cases/{slug}/attempts is throttled per client IP.
- At most `LLM_DRAFTS_PER_DAY` AI drafts are ingested per UTC day.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.config import get_settings
from app.db.engine import get_engine
from app.main import create_app
from app.repository.extract_cache import reserve_run
from pipeline.cache import get_extract_cache
from pipeline.providers.fake import SAMPLE_TEXT_FILE, FakeProvider

pytestmark = pytest.mark.db

SAMPLE = SAMPLE_TEXT_FILE.read_text().strip()
SOURCE = "Sudden breathlessness after a 14-hour flight; left calf is swollen and tender."
TODAY_EXTRACT_COUNT = text(
    "SELECT count FROM daily_usage "
    "WHERE kind = 'extract' AND day = (now() AT TIME ZONE 'UTC')::date"
)


@pytest.fixture(autouse=True)
def fake_llm_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("PIPELINE_FAKE_LLM", "1")
    monkeypatch.setenv("EXTRACT_RATE_PER_MINUTE", "100")
    monkeypatch.setenv("EXTRACT_DAILY_CAP", "2")
    monkeypatch.delenv("EXTRACT_CACHE_DIR", raising=False)
    get_settings.cache_clear()
    get_extract_cache.cache_clear()
    yield
    get_extract_cache.cache_clear()


@asynccontextmanager
async def fresh_instance(engine: AsyncEngine) -> AsyncIterator[httpx.AsyncClient]:
    """A new app: empty in-memory windows, like a Cloud Run instance after scale to zero."""
    app = create_app()
    app.dependency_overrides[get_engine] = lambda: engine
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http


def extract(client: httpx.AsyncClient, note: str) -> Any:
    return client.post("/api/extract", json={"text": f"{SAMPLE} {note}", "provider": "gemini"})


async def test_the_daily_extraction_budget_survives_a_restart(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    assert (await extract(client, "One.")).status_code == 200
    assert (await extract(client, "Two.")).status_code == 200
    refused = await extract(client, "Three.")
    assert refused.status_code == 429
    assert "daily extraction budget" in refused.json()["detail"]

    get_extract_cache.cache_clear()  # the restarted instance has an empty LRU too
    async with fresh_instance(engine) as restarted:
        assert (await extract(restarted, "Four.")).status_code == 429
        assert (await extract(restarted, "One.")).status_code == 200  # cached: free

    async with engine.connect() as conn:
        assert await conn.scalar(TODAY_EXTRACT_COUNT) == 2


async def test_a_failed_run_spends_the_budget_too(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    providers = iter(
        [FakeProvider(name="gemini", model="fake-gemini", script=["{", "{", "{"])]
        + [FakeProvider.default(name="gemini", model="fake-gemini")]
    )
    monkeypatch.setattr("app.routers.extract.get_provider", lambda *args: next(providers))
    assert (await extract(client, "One.")).status_code == 502  # paid for, nothing to show
    assert (await extract(client, "Two.")).status_code == 200
    assert (await extract(client, "Three.")).status_code == 429


async def test_reservations_never_overshoot_the_cap(engine: AsyncEngine) -> None:
    granted = await asyncio.gather(*(reserve_run(engine, cap=3) for _ in range(10)))
    assert sum(granted) == 3
    assert await reserve_run(engine, cap=0) is False


async def create(client: httpx.AsyncClient, case: dict[str, Any]) -> httpx.Response:
    return await client.post("/api/cases", json=case)


def attempt() -> dict[str, Any]:
    return {"choices": {}, "diagnosis_text": "Pneumothorax", "confidence": 3}


async def test_attempts_are_throttled_per_client_ip(
    engine: AsyncEngine, case_pe: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.ratelimit.ATTEMPTS_PER_MINUTE", 3)
    monkeypatch.setenv("INTERNAL_API_KEY", "k3y")
    get_settings.cache_clear()
    async with fresh_instance(engine) as client:
        slug = (await create(client, case_pe)).json()["slug"]
        url = f"/api/cases/{slug}/attempts"
        # Direct callers: a spoofed first entry does not buy a new bucket (Cloud Run appends
        # the real peer last).
        spoofed = [
            await client.post(
                url, json=attempt(), headers={"X-Forwarded-For": f"10.0.0.{i}, 198.51.100.9"}
            )
            for i in range(4)
        ]
        assert [r.status_code for r in spoofed] == [201, 201, 201, 429]
        assert spoofed[-1].json()["title"] == "Too many requests"
        assert "attempts per minute" in spoofed[-1].json()["detail"]
        # The web server (holds the key) names each browser's address: separate buckets.
        web = {"X-Internal-Key": "k3y", "X-Forwarded-For": "203.0.113.7, 198.51.100.9"}
        assert (await client.post(url, json=attempt(), headers=web)).status_code == 201


def llm_draft(case_pe: dict[str, Any], n: int) -> dict[str, Any]:
    return {
        **case_pe,
        "title": f"{case_pe['title']} {n}",
        "source": {"kind": "llm", "provider": "gemini", "text": SOURCE},
    }


async def test_ai_drafts_are_capped_per_utc_day(
    client: httpx.AsyncClient,
    engine: AsyncEngine,
    case_pe: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.ratelimit.LLM_DRAFTS_PER_DAY", 2)
    assert (await create(client, llm_draft(case_pe, 1))).status_code == 201
    assert (await create(client, llm_draft(case_pe, 2))).status_code == 201
    refused = await create(client, llm_draft(case_pe, 3))
    assert refused.status_code == 429
    assert refused.headers["content-type"].startswith("application/problem+json")
    assert refused.json()["title"] == "Draft limit reached"
    assert "2 AI drafts" in refused.json()["detail"]

    # Publishing the same draft again is not a new draft; curated cases are not capped.
    assert (await create(client, llm_draft(case_pe, 2))).status_code == 200
    assert (await create(client, case_pe)).status_code == 201

    # Yesterday's drafts do not count against today.
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE cases SET created_at = now() - interval '1 day' WHERE source_kind = 'llm'")
        )
    assert (await create(client, llm_draft(case_pe, 3))).status_code == 201
