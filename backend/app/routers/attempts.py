from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Request

from app.db.engine import EngineDep
from app.problems import raise_problem
from app.ratelimit import RateLimited, client_ip, get_limits
from app.repository.attempts import attempt_result, record_attempt
from app.schemas.attempt import AttemptIn, AttemptResult
from app.schemas.common import ProblemDetail

router = APIRouter(tags=["attempts"])
Slug = Annotated[str, Path(pattern=r"^[a-z0-9-]{3,100}$")]


@router.post(
    "/cases/{slug}/attempts",
    status_code=201,
    response_model=AttemptResult,
    responses={
        404: {"model": ProblemDetail},
        422: {"model": ProblemDetail},
        429: {"model": ProblemDetail},
    },
)
async def create_attempt(
    slug: Slug, body: AttemptIn, request: Request, engine: EngineDep
) -> AttemptResult:
    # Anonymous and public: a per-IP window keeps a script from flooding the cohort (and the
    # sponsor view's "top wrong diagnoses") with made-up attempts.
    try:
        get_limits(request).attempts_per_ip.check(client_ip(request))
    except RateLimited as exc:
        raise_problem(429, "Too many requests", str(exc))
    async with engine.connect() as conn:
        # Answer key read + scoring + attempt and choices insert: one transaction (404 / 422
        # roll back). Cohort analytics run after the commit, so this attempt is in its cohort.
        recorded = await record_attempt(conn, slug, body)
        return await attempt_result(conn, recorded)
