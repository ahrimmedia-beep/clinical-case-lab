"""Postgres-backed layer for the POST /api/extract result cache (spec §10 step 2).

Makes a warm cache survive a Cloud Run instance restart: `pipeline.cache.ExtractCache` is an
in-memory LRU per process, lost whenever an idle (`min-instances=0`) instance sleeps. These two
functions are the read-through / write-through to Postgres underneath it, called from
`app.routers.extract`. Both run a single statement and are safe to call on every request; the
caller treats a `SQLAlchemyError` from either one as a cache miss, never as a request failure.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.tables import extract_cache
from app.schemas.extract import ExtractResponse


async def lookup(engine: AsyncEngine, key: str) -> ExtractResponse | None:
    async with engine.connect() as conn:
        row = (
            await conn.execute(select(extract_cache.c.response).where(extract_cache.c.key == key))
        ).scalar_one_or_none()
    return None if row is None else ExtractResponse.model_validate(row)


async def store(
    engine: AsyncEngine,
    *,
    key: str,
    provider: str,
    model: str,
    prompt_version: str,
    response: ExtractResponse,
) -> None:
    # ON CONFLICT DO NOTHING: the key is a content hash, so a second writer racing the first
    # (two instances resolving the same cold text at once) agrees with it rather than erroring.
    stmt = (
        pg_insert(extract_cache)
        .values(
            key=key,
            provider=provider,
            model=model,
            prompt_version=prompt_version,
            response=response.model_dump(mode="json"),
        )
        .on_conflict_do_nothing(index_elements=[extract_cache.c.key])
    )
    async with engine.begin() as conn:
        await conn.execute(stmt)
