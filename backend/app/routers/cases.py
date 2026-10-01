from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Response

from app.problems import raise_problem
from app.schemas.attempt import RevealIn, RevealOut
from app.schemas.case import CaseCreated, CasePublic, CaseSummary, ClinicalCase
from app.schemas.common import ProblemDetail
from app.security import require_ingest_key

router = APIRouter(tags=["cases"])
Slug = Annotated[str, Path(pattern=r"^[a-z0-9-]{3,100}$")]
ERRORS: dict[int | str, dict[str, Any]] = {
    404: {"model": ProblemDetail},
    413: {"model": ProblemDetail},
    422: {"model": ProblemDetail},
}


@router.post(
    "/cases",
    status_code=201,
    response_model=CaseCreated,
    dependencies=[Depends(require_ingest_key)],
    responses={
        200: {"model": CaseCreated, "description": "Identical case already stored"},
        401: {"model": ProblemDetail},
        **ERRORS,
    },
)
async def create_case(case: ClinicalCase, response: Response) -> CaseCreated:
    raise_problem(501, "Not implemented yet")


@router.get("/cases", response_model=list[CaseSummary])
async def list_cases() -> list[CaseSummary]:
    raise_problem(501, "Not implemented yet")


@router.get("/cases/{slug}", response_model=CasePublic, responses=ERRORS)
async def get_case(slug: Slug) -> CasePublic:
    raise_problem(501, "Not implemented yet")


@router.post("/cases/{slug}/reveal", response_model=list[RevealOut], responses=ERRORS)
async def reveal_options(slug: Slug, body: RevealIn) -> list[RevealOut]:
    raise_problem(501, "Not implemented yet")
