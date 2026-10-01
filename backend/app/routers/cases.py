from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Request, Response
from sqlalchemy.ext.asyncio import AsyncEngine

from app import ratelimit
from app.case_views import build_reveals
from app.config import get_settings
from app.db.engine import EngineDep
from app.problems import raise_problem
from app.repository import cases as cases_repo
from app.repository import review as review_repo
from app.schemas.attempt import MultiSelectStage, RevealIn, RevealOut
from app.schemas.case import CaseCreated, CasePublic, CaseSummary, ClinicalCase, SourceKind
from app.schemas.common import ProblemDetail
from app.scoring import unknown_choices
from app.security import require_ingest_key
from app.stages import Stage

router = APIRouter(tags=["cases"])
Slug = Annotated[str, Path(pattern=r"^[a-z0-9-]{3,100}$")]
ERRORS: dict[int | str, dict[str, Any]] = {
    404: {"model": ProblemDetail},
    413: {"model": ProblemDetail},
    422: {"model": ProblemDetail},
}


async def limit_case_body(request: Request) -> None:
    """Reject case JSON above `max_case_bytes` (256 KB) with 413 before it is validated."""
    limit = get_settings().max_case_bytes
    detail = f"A case must be at most {limit} bytes."
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > limit:
        raise_problem(413, "Payload too large", detail)
    if len(await request.body()) > limit:
        raise_problem(413, "Payload too large", detail)


async def _within_draft_cap(case: ClinicalCase, engine: AsyncEngine) -> None:
    """429 once today's (UTC) AI drafts reach the cap. Re-publishing a stored draft is not new."""
    cap = ratelimit.LLM_DRAFTS_PER_DAY
    async with engine.connect() as conn:
        if await review_repo.is_stored(conn, case):
            return
        if await review_repo.llm_drafts_today(conn) >= cap:
            raise_problem(
                429,
                "Draft limit reached",
                f"At most {cap} AI drafts can be published per day (UTC); try again tomorrow.",
            )


@router.post(
    "/cases",
    status_code=201,
    response_model=CaseCreated,
    dependencies=[Depends(require_ingest_key), Depends(limit_case_body)],
    responses={
        200: {"model": CaseCreated, "description": "Identical case already stored"},
        401: {"model": ProblemDetail},
        **ERRORS,
        429: {"model": ProblemDetail},
    },
)
async def create_case(case: ClinicalCase, response: Response, engine: EngineDep) -> CaseCreated:
    if case.source is not None and case.source.kind is SourceKind.LLM:
        await _within_draft_cap(case, engine)
    async with engine.connect() as conn:
        created = await cases_repo.insert_case(conn, case)
    if created.created:
        response.headers["Location"] = f"/api/cases/{created.slug}"
    else:
        response.status_code = 200
    return created


@router.get("/cases", response_model=list[CaseSummary])
async def list_cases(engine: EngineDep) -> list[CaseSummary]:
    async with engine.connect() as conn:
        return await cases_repo.list_cases(conn)


@router.get("/cases/{slug}", response_model=CasePublic, responses=ERRORS)
async def get_case(slug: Slug, engine: EngineDep) -> CasePublic:
    async with engine.connect() as conn:
        public = await cases_repo.get_case_public(conn, slug)
    if public is None:
        raise_problem(404, "Case not found", f"No case with slug '{slug}'.")
    return public


@router.post("/cases/{slug}/reveal", response_model=list[RevealOut], responses=ERRORS)
async def reveal_options(slug: Slug, body: RevealIn, engine: EngineDep) -> list[RevealOut]:
    async with engine.connect() as conn:
        loaded = await cases_repo.load_case(conn, slug)
    if loaded is None:
        raise_problem(404, "Case not found", f"No case with slug '{slug}'.")
    _, case = loaded
    problems = unknown_choices(case, {MultiSelectStage(body.stage): body.option_keys})
    if problems:
        raise_problem(422, "Invalid choices", "; ".join(problems))
    return build_reveals(case, Stage(body.stage), body.option_keys)
