"""Let an AI model play a stored case blinded. Internal key only (seed scripts, web server)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path

from app.problems import raise_problem
from app.schemas.ai_player import AiAttemptRequest, AiAttemptSummary
from app.schemas.common import ProblemDetail
from app.security import require_internal_key

router = APIRouter(tags=["ai-players"], dependencies=[Depends(require_internal_key)])
Slug = Annotated[str, Path(pattern=r"^[a-z0-9-]{3,100}$")]


@router.post(
    "/cases/{slug}/ai-attempts",
    status_code=201,
    response_model=AiAttemptSummary,
    responses={
        401: {"model": ProblemDetail},
        404: {"model": ProblemDetail},
        502: {"model": ProblemDetail},
        503: {"model": ProblemDetail},
    },
)
async def create_ai_attempt(slug: Slug, body: AiAttemptRequest) -> AiAttemptSummary:
    raise_problem(501, "Not implemented yet")
