"""Physician review gate for AI-drafted cases. Internal key only (called by the web server)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path

from app.db.engine import EngineDep
from app.problems import raise_problem
from app.repository.review import approve_case as approve_draft
from app.repository.review import get_case_review as load_review
from app.schemas.common import ProblemDetail
from app.schemas.review import ApproveResponse, CaseReview
from app.security import require_internal_key

router = APIRouter(tags=["review"], dependencies=[Depends(require_internal_key)])
Slug = Annotated[str, Path(pattern=r"^[a-z0-9-]{3,100}$")]
ERRORS: dict[int | str, dict[str, Any]] = {
    401: {"model": ProblemDetail},
    404: {"model": ProblemDetail},
    409: {"model": ProblemDetail},
}


@router.get("/cases/{slug}/review", response_model=CaseReview, responses=ERRORS)
async def get_case_review(slug: Slug, engine: EngineDep) -> CaseReview:
    # Answer key + checklist for any case; `review_status` tells the page whether to offer
    # "Approve". Approving twice is the 409.
    async with engine.connect() as conn:
        review = await load_review(conn, slug)
    if review is None:
        raise_problem(404, "Case not found", f"No case with slug '{slug}'.")
    return review


@router.post("/cases/{slug}/approve", response_model=ApproveResponse, responses=ERRORS)
async def approve_case(slug: Slug, engine: EngineDep) -> ApproveResponse:
    async with engine.connect() as conn:
        return await approve_draft(conn, slug)
