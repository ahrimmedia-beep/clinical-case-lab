"""Let an AI model play a stored case blinded. Internal key only (seed scripts, web server).

The model sees `CasePublic` and the reveals of the options it chose, exactly like a physician,
and its answer is scored and stored by the same `record_attempt` path, labelled `ai:<model>`.
AI attempts are excluded from the cohort percentile and pick rates; they appear as benchmarks.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Path

from app.case_views import build_case_public, build_reveals
from app.config import get_settings
from app.db.engine import EngineDep
from app.problems import raise_problem
from app.repository.attempts import AI_LABEL_PREFIX, record_attempt
from app.repository.cases import load_stored_case
from app.schemas.ai_player import AiAttemptRequest, AiAttemptSummary
from app.schemas.attempt import RevealOut
from app.schemas.common import ProblemDetail
from app.security import require_internal_key
from app.stages import Stage
from pipeline.ai_player import play_case
from pipeline.factory import UnknownModel, get_provider, resolve_model
from pipeline.providers.base import ProviderError, ProviderUnavailable, public_detail

router = APIRouter(tags=["ai-players"], dependencies=[Depends(require_internal_key)])
log = structlog.get_logger()
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
async def create_ai_attempt(
    slug: Slug, body: AiAttemptRequest, engine: EngineDep
) -> AiAttemptSummary:
    try:
        model = resolve_model(body.provider, body.model)
    except UnknownModel as exc:
        raise_problem(422, "Unknown model", str(exc))

    # Short connections: none is held while the model thinks (pool size 5 per instance).
    async with engine.connect() as conn:
        stored = await load_stored_case(conn, slug)
    if stored is None:
        raise_problem(404, "Case not found", f"No case with slug '{slug}'.")
    public = build_case_public(
        stored.id, stored.slug, stored.case, review_status=stored.review_status
    )

    async def reveal(stage: str, keys: Sequence[str]) -> list[RevealOut]:
        # The same server-side function as POST /reveal: chosen options only, no correctness.
        return build_reveals(stored.case, Stage(stage), keys)

    try:
        provider = get_provider(body.provider, model, get_settings())
        play = await play_case(public, reveal, provider)
    except ProviderUnavailable as exc:
        # The SDK's text stays in the server log; the client gets a fixed, provider-neutral line.
        log.warning(
            "ai_attempt_unavailable",
            provider=body.provider.value,
            status=exc.status,
            error=str(exc),
        )
        raise_problem(503, "Model provider unavailable", public_detail(exc))
    except ProviderError as exc:
        log.warning(
            "ai_attempt_failed",
            provider=body.provider.value,
            error_type=type(exc).__name__,
            error=str(exc),
        )
        raise_problem(502, "The model's answer could not be used", public_detail(exc))

    label = f"{AI_LABEL_PREFIX}{model}"
    async with engine.connect() as conn:
        recorded = await record_attempt(conn, stored.slug, play.attempt, simulated_label=label)
    score = recorded.score
    return AiAttemptSummary(
        attempt_id=recorded.attempt_id,
        label=label,
        provider=body.provider.value,
        model=model,
        points=score.points,
        max_points=score.max_points,
        diagnosis_text=play.attempt.diagnosis_text,
        diagnosis_correct=score.diagnosis.correct,
        confidence=play.attempt.confidence,
        calibration=score.diagnosis.calibration,
        latency_ms=play.usage.latency_ms,
        cost_usd=play.usage.cost_usd,
    )
