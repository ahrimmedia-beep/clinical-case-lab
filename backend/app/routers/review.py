"""Physician review gate for AI-drafted cases. Internal key only (called by the web server)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path

from app.problems import raise_problem
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
async def get_case_review(slug: Slug) -> CaseReview:
    raise_problem(501, "Not implemented yet")


@router.post("/cases/{slug}/approve", response_model=ApproveResponse, responses=ERRORS)
async def approve_case(slug: Slug) -> ApproveResponse:
    raise_problem(501, "Not implemented yet")
