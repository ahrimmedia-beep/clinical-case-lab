"""POST /api/extract: raw clinical text -> LLM-built case with verbatim evidence spans."""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.config import get_settings
from app.db.engine import EngineDep
from app.problems import raise_problem
from app.ratelimit import Limits, RateLimited, client_ip, daily_budget_used_up, get_limits
from app.repository import extract_cache as extract_cache_db
from app.schemas.common import ProblemDetail
from app.schemas.extract import ExtractRequest, ExtractResponse
from app.security import require_internal_key
from pipeline.cache import cache_key, get_extract_cache
from pipeline.factory import UnknownModel, get_provider, resolve_model
from pipeline.phi import PhiLeakError
from pipeline.prompts import PROMPT_VERSION
from pipeline.providers.base import ProviderError, ProviderUnavailable, public_detail
from pipeline.run import run_pipeline

router = APIRouter(tags=["pipeline"])
log = structlog.get_logger()


# Postgres being unreachable can surface as a raw driver/socket error (e.g. asyncpg raises
# ConnectionRefusedError, an OSError, before SQLAlchemy gets a chance to wrap it) rather than
# a SQLAlchemyError, so both are treated as "no cache today" — never as a request failure.
DB_CACHE_ERRORS = (OSError, TimeoutError, SQLAlchemyError)


async def _db_lookup(engine: AsyncEngine, key: str) -> ExtractResponse | None:
    """Postgres read-through under the in-memory LRU. A DB error is a miss, not a failure."""
    try:
        return await extract_cache_db.lookup(engine, key)
    except DB_CACHE_ERRORS as exc:
        log.warning("extract_cache_db_lookup_failed", error=type(exc).__name__)
        return None


async def _db_store(
    engine: AsyncEngine, *, key: str, provider: str, model: str, response: ExtractResponse
) -> None:
    """Postgres write-through after a successful run. A DB error here never fails the request."""
    try:
        await extract_cache_db.store(
            engine,
            key=key,
            provider=provider,
            model=model,
            prompt_version=PROMPT_VERSION,
            response=response,
        )
    except DB_CACHE_ERRORS as exc:
        log.warning("extract_cache_db_store_failed", error=type(exc).__name__)


async def _reserve_paid_run(engine: AsyncEngine, limits: Limits) -> None:
    """One slot of today's budget (Postgres), or RateLimited. If Postgres cannot be reached, the
    instance's in-memory day budget stands in, so a DB outage never lifts the cap."""
    try:
        granted = await extract_cache_db.reserve_run(engine, cap=get_settings().extract_daily_cap)
    except DB_CACHE_ERRORS as exc:
        log.warning("extract_budget_db_failed", error=type(exc).__name__)
        limits.extract_day_fallback.take()
        return
    if not granted:
        raise daily_budget_used_up()


@router.post(
    "/extract",
    response_model=ExtractResponse,
    responses={
        401: {"model": ProblemDetail},
        422: {"model": ProblemDetail},
        429: {"model": ProblemDetail},
        502: {"model": ProblemDetail},
        503: {"model": ProblemDetail},
    },
    # The key check reads the header from the request, so unauthenticated calls stop here
    # (401) and the OpenAPI document stays exactly as the contracts froze it.
    dependencies=[Depends(require_internal_key)],
)
async def extract_case(
    body: ExtractRequest,
    request: Request,
    engine: EngineDep,
    x_internal_key: Annotated[str | None, Header()] = None,  # documents the header; checked above
) -> ExtractResponse:
    # Order: 401 key -> 422 unknown model -> cached answer (free, instant) -> 429 per-IP window
    # -> 429 daily budget (Postgres) -> 422 PHI residue -> 503 provider unavailable
    # -> 502 unusable answer -> 200.
    # (A comment, not a docstring: a docstring would change the frozen OpenAPI document.)
    try:
        model = resolve_model(body.provider, body.model)
    except UnknownModel as exc:
        raise_problem(422, "Unknown model", str(exc))
    cache = get_extract_cache()
    key = cache_key(body.text, body.provider.value, model, PROMPT_VERSION)
    cached = cache.get(key)
    if cached is None:
        cached = await _db_lookup(engine, key)
        if cached is not None:
            cache.remember(key, cached)  # warm this instance's LRU; already in Postgres
    if cached is not None:
        log.info("extract_cache_hit", provider=body.provider.value, model=model)
        return cached
    limits = get_limits(request)
    try:  # only real model calls spend the budgets
        limits.extract_per_ip.check(client_ip(request))
        await _reserve_paid_run(engine, limits)
    except RateLimited as exc:
        raise_problem(429, "Too many requests", str(exc))
    try:
        provider = get_provider(body.provider, model, get_settings())
        response = await run_pipeline(body.text, provider)
    except UnknownModel as exc:
        raise_problem(422, "Unknown model", str(exc))
    except PhiLeakError as exc:
        raise_problem(422, "Identifiers remain after masking", str(exc))
    except ProviderUnavailable as exc:
        # The SDK's text stays in the server log; the client gets a fixed, provider-neutral line.
        log.warning(
            "extract_unavailable", provider=body.provider.value, status=exc.status, error=str(exc)
        )
        raise_problem(503, "Model provider unavailable", public_detail(exc))
    except ProviderError as exc:
        log.warning(
            "extract_failed",
            provider=body.provider.value,
            error_type=type(exc).__name__,
            error=str(exc),
        )
        raise_problem(502, "The model's answer could not be used", public_detail(exc))
    cache.put(key, response)
    await _db_store(engine, key=key, provider=body.provider.value, model=model, response=response)
    return response
