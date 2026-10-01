"""Postgres fixtures for tests marked `db`. Skips cleanly when the database is unreachable."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from app.db.engine import get_engine
from app.main import create_app
from tests.db.support import TABLES, TEST_DATABASE_URL, run_alembic


async def _ensure_database() -> None:
    url = make_url(TEST_DATABASE_URL)
    admin = create_async_engine(
        url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
        connect_args={"timeout": 3},
    )
    try:
        async with admin.connect() as conn:
            exists = await conn.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": url.database}
            )
            if not exists:
                await conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    finally:
        await admin.dispose()


# Several test runs can share one test database (parallel work in one checkout, CI retries).
# Each run holds this advisory lock for its whole DB session, so runs take turns instead of
# truncating or migrating under each other.
SESSION_LOCK_KEY = 4_200_917


@pytest.fixture(scope="session")
async def db_engine() -> AsyncIterator[AsyncEngine]:
    try:
        await _ensure_database()
    except (OSError, TimeoutError, SQLAlchemyError) as exc:
        safe = make_url(TEST_DATABASE_URL).render_as_string(hide_password=True)
        pytest.skip(
            f"Postgres not reachable at {safe} ({type(exc).__name__}); "
            "start it with `make db` or set TEST_DATABASE_URL"
        )
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with engine.connect() as lock_conn:
        await lock_conn.execute(text("SET lock_timeout = '300s'"))
        await lock_conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": SESSION_LOCK_KEY})
        await lock_conn.commit()
        try:
            run_alembic("upgrade", "head")
            yield engine
        finally:
            await lock_conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": SESSION_LOCK_KEY})
            await lock_conn.commit()
    await engine.dispose()


@pytest.fixture
async def engine(db_engine: AsyncEngine) -> AsyncIterator[AsyncEngine]:
    async with db_engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))
    yield db_engine


@pytest.fixture
async def conn(engine: AsyncEngine) -> AsyncIterator[AsyncConnection]:
    async with engine.connect() as connection:
        yield connection


@pytest.fixture
async def client(engine: AsyncEngine) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()
    app.dependency_overrides[get_engine] = lambda: engine
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http
