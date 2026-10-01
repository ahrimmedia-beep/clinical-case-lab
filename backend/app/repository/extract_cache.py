"""Postgres-backed layer for POST /api/extract: the result cache (spec §10 step 2) and the
daily budget of paid runs.

Makes a warm cache survive a Cloud Run instance restart: `pipeline.cache.ExtractCache` is an
in-memory LRU per process, lost whenever an idle (`min-instances=0`) instance sleeps. These two
functions are the read-through / write-through to Postgres underneath it, called from
`app.routers.extract`. Both are safe to call on every request; the caller treats a
`SQLAlchemyError` from either one as a cache miss, never as a request failure.

A stored row that no longer validates (the response schema changed without a `PROMPT_VERSION`
bump) is a miss too: `lookup` drops it, so the next successful run writes a fresh row in its place
instead of the text failing with a 500 forever.

`reserve_run` is the daily budget: one `daily_usage` row per UTC day, bumped by a conditional
upsert before every paid model run. A run that later fails still spent its slot (failed calls
are billed too), and a cache hit never reserves one.
"""

from __future__ import annotations

import structlog
from pydantic import ValidationError
from sqlalchemy import Date, cast, delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.tables import daily_usage, extract_cache
from app.schemas.extract import ExtractResponse

log = structlog.get_logger()


async def lookup(engine: AsyncEngine, key: str) -> ExtractResponse | None:
    async with engine.connect() as conn:
        row = (
            await conn.execute(select(extract_cache.c.response).where(extract_cache.c.key == key))
        ).scalar_one_or_none()
    if row is None:
        return None
    try:
        return ExtractResponse.model_validate(row)
    except ValidationError as exc:
        log.warning("extract_cache_db_row_invalid", errors=exc.error_count())
        async with engine.begin() as conn:
            await conn.execute(delete(extract_cache).where(extract_cache.c.key == key))
        return None


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


async def reserve_run(engine: AsyncEngine, *, cap: int, kind: str = "extract") -> bool:
    """Take one of today's (UTC) `cap` slots; False when they are all taken.

    A single statement, so concurrent callers never overshoot: the upsert increments only while
    `count < cap`, and returns no row once the day is full.
    """
    if cap <= 0:
        return False
    today = cast(func.timezone("UTC", func.now()), Date)
    stmt = (
        pg_insert(daily_usage)
        .values(day=today, kind=kind, count=1)
        .on_conflict_do_update(
            index_elements=[daily_usage.c.day, daily_usage.c.kind],
            set_={"count": daily_usage.c.count + 1},
            where=daily_usage.c.count < cap,
        )
        .returning(daily_usage.c.count)
    )
    async with engine.begin() as conn:
        return (await conn.execute(stmt)).scalar_one_or_none() is not None
