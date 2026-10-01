"""POST /api/extract result cache, Postgres layer (spec: survive a Cloud Run instance restart).

`pipeline.cache.ExtractCache` is an in-memory LRU per process; `app.repository.extract_cache`
mirrors a hit into Postgres so a fresh instance (an empty LRU) still answers from the cache
instead of paying for the LLM again. Fake provider only; these tests never call a paid API.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.config import get_settings
from app.db.tables import extract_cache
from app.repository import extract_cache as extract_cache_db
from app.schemas.extract import ExtractResponse
from pipeline.cache import cache_key, get_extract_cache
from pipeline.prompts import PROMPT_VERSION
from pipeline.providers.fake import SAMPLE_TEXT_FILE, FakeProvider
from pipeline.run import run_pipeline

pytestmark = pytest.mark.db

SAMPLE = SAMPLE_TEXT_FILE.read_text().strip()  # ExtractRequest (str_strip_whitespace) stores it
# trimmed; the cache key must be computed from that exact string to land on the same row.


@pytest.fixture(autouse=True)
def fake_llm_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PIPELINE_FAKE_LLM", "1")
    monkeypatch.setenv("EXTRACT_RATE_PER_MINUTE", "2")
    monkeypatch.delenv("EXTRACT_CACHE_DIR", raising=False)
    get_settings.cache_clear()
    get_extract_cache.cache_clear()
    yield
    get_extract_cache.cache_clear()


def post(client: httpx.AsyncClient, **body: Any) -> Any:
    payload = {"text": SAMPLE, "provider": "gemini", **body}
    return client.post("/api/extract", json=payload)


async def test_db_hit_after_memory_cache_reset_skips_provider_and_rate_limit(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    async def counting(text: str, provider: Any, author: Any = None) -> Any:
        calls.append(provider.model)
        return await run_pipeline(text, provider, author)

    monkeypatch.setattr("app.routers.extract.run_pipeline", counting)

    # Call 1: a genuine miss. Runs the (fake) model and spends slot 1 of the 2/minute budget,
    # and (per app.routers.extract) writes through to Postgres.
    first = await post(client)
    assert first.status_code == 200, first.text
    assert calls == ["fake-gemini"]

    # Simulate a fresh Cloud Run instance: the in-memory LRU is gone, Postgres is not.
    get_extract_cache.cache_clear()

    # Call 2: same text/provider/model -> must be served from Postgres: same body, the
    # pipeline does not run again, and the rate limiter is not touched.
    second = await post(client)
    assert second.status_code == 200, second.text
    assert second.json() == first.json()
    assert calls == ["fake-gemini"]

    # Call 3: a genuinely new request (different text). If call 2 had wrongly spent a slot,
    # the 2/minute budget would already be exhausted and this would be 429.
    third = await post(client, text=f"{SAMPLE} Note three.")
    assert third.status_code == 200, third.text
    assert calls == ["fake-gemini", "fake-gemini"]

    # Call 4: now the budget (2 real calls: #1 and #3) is exhausted.
    fourth = await post(client, text=f"{SAMPLE} Note four.")
    assert fourth.status_code == 429, fourth.text


async def test_different_model_provider_or_prompt_version_is_a_postgres_miss(
    engine: AsyncEngine,
) -> None:
    response = await run_pipeline(SAMPLE, FakeProvider.default())
    stored_key = cache_key(SAMPLE, "gemini", "fake-gemini", PROMPT_VERSION)
    await extract_cache_db.store(
        engine,
        key=stored_key,
        provider="gemini",
        model="fake-gemini",
        prompt_version=PROMPT_VERSION,
        response=response,
    )

    assert await extract_cache_db.lookup(engine, stored_key) == response
    other_provider = cache_key(SAMPLE, "claude", "fake-gemini", PROMPT_VERSION)
    other_model = cache_key(SAMPLE, "gemini", "fake-claude", PROMPT_VERSION)
    other_prompt = cache_key(SAMPLE, "gemini", "fake-gemini", "v2")
    for miss_key in (other_provider, other_model, other_prompt):
        assert await extract_cache_db.lookup(engine, miss_key) is None


async def test_db_lookup_failure_falls_back_to_running_the_pipeline(
    client: httpx.AsyncClient, engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def boom(*args: object, **kwargs: object) -> ExtractResponse | None:
        raise SQLAlchemyError("connection reset (simulated)")

    monkeypatch.setattr("app.routers.extract.extract_cache_db.lookup", boom)

    response = await post(client)
    assert response.status_code == 200, response.text

    # The write path does not go through the broken lookup, so the successful run still landed
    # in Postgres: a second call (lookup restored) is served from there.
    monkeypatch.undo()
    get_extract_cache.cache_clear()
    key = cache_key(SAMPLE, "gemini", "fake-gemini", PROMPT_VERSION)
    assert await extract_cache_db.lookup(engine, key) == ExtractResponse.model_validate(
        response.json()
    )


async def test_a_stored_row_that_no_longer_validates_is_a_miss_and_is_replaced(
    client: httpx.AsyncClient, engine: AsyncEngine
) -> None:
    # A schema change without a PROMPT_VERSION bump leaves rows the new ExtractResponse rejects.
    key = cache_key(SAMPLE, "gemini", "fake-gemini", PROMPT_VERSION)
    async with engine.begin() as conn:
        await conn.execute(
            extract_cache.insert().values(
                key=key, provider="gemini", model="fake-gemini", response={"stale": True}
            )
        )
    assert await extract_cache_db.lookup(engine, key) is None

    response = await post(client)
    assert response.status_code == 200, response.text
    # The fresh run replaced the stale row, so the next cold instance is served from Postgres.
    assert await extract_cache_db.lookup(engine, key) == ExtractResponse.model_validate(
        response.json()
    )
