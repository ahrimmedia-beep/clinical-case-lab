"""Sponsor view of a case's decision points. Internal key only (called by the web server)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path

from app.db.engine import EngineDep
from app.problems import raise_problem
from app.repository.insights import case_insights
from app.schemas.common import ProblemDetail
from app.schemas.insights import CaseInsights
from app.security import require_internal_key

router = APIRouter(tags=["insights"], dependencies=[Depends(require_internal_key)])
Slug = Annotated[str, Path(pattern=r"^[a-z0-9-]{3,100}$")]


@router.get(
    "/cases/{slug}/insights",
    response_model=CaseInsights,
    responses={401: {"model": ProblemDetail}, 404: {"model": ProblemDetail}},
)
async def get_case_insights(slug: Slug, engine: EngineDep) -> CaseInsights:
    # Humans + simulated cohort only; AI players are listed as benchmarks.
    async with engine.connect() as conn:
        insights = await case_insights(conn, slug)
    if insights is None:
        raise_problem(404, "Case not found", f"No case with slug '{slug}'.")
    return insights
