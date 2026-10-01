"""POST /api/extract: raw clinical text -> LLM-built case with verbatim evidence spans."""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Header, Request

from app.config import get_settings
from app.problems import raise_problem
from app.ratelimit import RateLimited, client_ip, get_limiter
from app.schemas.common import ProblemDetail
from app.schemas.extract import ExtractRequest, ExtractResponse
from app.security import require_internal_key
from pipeline.cache import cache_key, get_extract_cache
from pipeline.factory import UnknownModel, get_provider, resolve_model
from pipeline.phi import PhiLeakError
from pipeline.prompts import PROMPT_VERSION
from pipeline.providers.base import ProviderError, ProviderUnavailable
from pipeline.run import run_pipeline

router = APIRouter(tags=["pipeline"])
log = structlog.get_logger()


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
    x_internal_key: Annotated[str | None, Header()] = None,  # documents the header; checked above
) -> ExtractResponse:
    # Order: 401 key -> 422 unknown model -> cached answer (free, instant) -> 429 rate limit
    # -> 422 PHI residue -> 503 provider unavailable -> 502 unusable answer -> 200.
    # (A comment, not a docstring: a docstring would change the frozen OpenAPI document.)
    try:
        model = resolve_model(body.provider, body.model)
    except UnknownModel as exc:
        raise_problem(422, "Unknown model", str(exc))
    cache = get_extract_cache()
    key = cache_key(body.text, body.provider.value, model, PROMPT_VERSION)
    cached = cache.get(key)
    if cached is not None:
        log.info("extract_cache_hit", provider=body.provider.value, model=model)
        return cached
    try:
        get_limiter().check(client_ip(request))  # only real model calls spend the budget
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
        log.warning("extract_unavailable", provider=body.provider.value, status=exc.status)
        raise_problem(503, "Model provider unavailable", str(exc))
    except ProviderError as exc:
        log.warning("extract_failed", provider=body.provider.value, error=type(exc).__name__)
        raise_problem(502, "The model's answer could not be used", str(exc))
    cache.put(key, response)
    return response
