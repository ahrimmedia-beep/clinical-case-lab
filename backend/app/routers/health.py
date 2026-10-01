from __future__ import annotations

import asyncio

import structlog
from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.engine import EngineDep
from app.problems import raise_problem

router = APIRouter(tags=["health"])
log = structlog.get_logger()


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(engine: EngineDep) -> dict[str, str]:
    # Readiness: the database answers `SELECT 1` within 2 s, otherwise 503. (A comment, not a
    # docstring: docstrings become OpenAPI descriptions and the contract is frozen.)
    try:
        async with asyncio.timeout(2):
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
    except (SQLAlchemyError, OSError, TimeoutError) as exc:
        log.warning("readyz_failed", error_type=type(exc).__name__)
        raise_problem(503, "Database unavailable")
    return {"status": "ok"}
