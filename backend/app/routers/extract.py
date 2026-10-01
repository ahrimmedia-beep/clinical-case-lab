from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header

from app.problems import raise_problem
from app.schemas.common import ProblemDetail
from app.schemas.extract import ExtractRequest, ExtractResponse

router = APIRouter(tags=["pipeline"])


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
)
async def extract_case(
    body: ExtractRequest,
    x_internal_key: Annotated[str | None, Header()] = None,
) -> ExtractResponse:
    raise_problem(501, "Not implemented yet")
