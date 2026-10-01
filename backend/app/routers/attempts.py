from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path

from app.problems import raise_problem
from app.schemas.attempt import AttemptIn, AttemptResult
from app.schemas.common import ProblemDetail

router = APIRouter(tags=["attempts"])
Slug = Annotated[str, Path(pattern=r"^[a-z0-9-]{3,100}$")]


@router.post(
    "/cases/{slug}/attempts",
    status_code=201,
    response_model=AttemptResult,
    responses={404: {"model": ProblemDetail}, 422: {"model": ProblemDetail}},
)
async def create_attempt(slug: Slug, body: AttemptIn) -> AttemptResult:
    raise_problem(501, "Not implemented yet")
