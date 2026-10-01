"""Attempts: one scoring + storing path (Core inserts) and cohort analytics (SQL files).

`record_attempt` is the only way an attempt reaches the database — physicians (API), the
simulated cohort (`seeds.simulate_cohort`) and AI players (`routers.ai_players`) all go through
it, so every attempt is scored by the same server-side code. Analytics (percentile, histogram,
pick rates) cover humans + the simulated cohort; AI players appear only as `benchmarks`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncConnection

from app.case_views import CohortStats, build_attempt_result
from app.db.queries import sql
from app.db.tables import attempt_choices, attempts, case_decisions, decision_options
from app.problems import raise_problem
from app.repository.cases import load_case
from app.schemas.attempt import AttemptIn, AttemptResult, Benchmark, HistogramBin
from app.schemas.case import ClinicalCase
from app.scoring import AttemptScore, calibrate, score_attempt, unknown_choices

MIN_COHORT_FOR_PERCENTILE = 5
AI_LABEL_PREFIX = "ai:"
COHORT_LABEL = "cohort"


@dataclass(frozen=True)
class CaseKey:
    """What scoring needs, loaded once: the case with its answer key and the option ids."""

    case_id: int
    slug: str
    case: ClinicalCase
    option_ids: Mapping[tuple[str, str], int]


@dataclass(frozen=True)
class RecordedAttempt:
    """A stored, scored attempt. `score` holds points, diagnosis verdict and calibration."""

    attempt_id: int
    case_id: int
    slug: str
    case: ClinicalCase
    score: AttemptScore


async def load_option_ids(conn: AsyncConnection, case_id: int) -> dict[tuple[str, str], int]:
    stmt = (
        select(case_decisions.c.stage, decision_options.c.key, decision_options.c.id)
        .join_from(
            case_decisions,
            decision_options,
            decision_options.c.decision_id == case_decisions.c.id,
        )
        .where(case_decisions.c.case_id == case_id)
    )
    rows = (await conn.execute(stmt)).all()
    return {(row.stage, row.key): int(row.id) for row in rows}


async def load_case_key(conn: AsyncConnection, slug: str) -> CaseKey | None:
    loaded = await load_case(conn, slug)
    if loaded is None:
        return None
    case_id, case = loaded
    return CaseKey(case_id, slug, case, await load_option_ids(conn, case_id))


async def insert_attempt(
    conn: AsyncConnection,
    *,
    case_id: int,
    attempt: AttemptIn,
    score: AttemptScore,
    option_ids: Mapping[tuple[str, str], int],
    is_simulated: bool = False,
    simulated_label: str | None = None,
) -> int:
    """Store the attempt and its choices. Low level: runs inside the caller's transaction."""
    attempt_id = await conn.scalar(
        insert(attempts)
        .values(
            case_id=case_id,
            points=score.points,
            max_points=score.max_points,
            right_count=score.right,
            wrong_count=score.wrong,
            missed_count=score.missed,
            harmful_count=score.harmful,
            diagnosis_text=attempt.diagnosis_text,
            diagnosis_correct=score.diagnosis.correct,
            confidence=attempt.confidence,
            duration_ms=attempt.duration_ms,
            is_simulated=is_simulated,
            simulated_label=simulated_label,
        )
        .returning(attempts.c.id)
    )
    rows = [
        {"attempt_id": attempt_id, "option_id": option_ids[(stage.value, key)]}
        for stage, keys in attempt.choices.items()
        for key in sorted(set(keys))
    ]
    if rows:
        await conn.execute(insert(attempt_choices), rows)
    return int(attempt_id)


async def record_attempt(
    conn: AsyncConnection,
    case: str | CaseKey,
    attempt: AttemptIn,
    *,
    simulated_label: str | None = None,
) -> RecordedAttempt:
    """Score an attempt against the stored answer key and store it with its choices.

    `case` is a slug (the answer key is read in the same transaction) or a preloaded `CaseKey`.
    `simulated_label`: `None` for a physician, `"cohort"` for the simulated cohort,
    `"ai:<model>"` for an AI player (e.g. `"ai:claude-opus-4-8"`); any label stores the attempt
    with `is_simulated = true`.

    Owns its transaction, like `insert_case`: call it on a connection with no transaction open
    (a fresh one, or after commit/rollback); SQLAlchemy raises if one is open, so a pending read
    transaction can never swallow the write. Raises `ProblemError` 404 for an unknown slug and
    422 naming unknown stages / option keys; nothing is written then.
    """
    async with conn.begin():
        key = case if isinstance(case, CaseKey) else await load_case_key(conn, case)
        if key is None:
            raise_problem(404, "Case not found", f"No case with slug '{case}'.")
        problems = unknown_choices(key.case, attempt.choices)
        if problems:
            raise_problem(422, "Invalid choices", "; ".join(problems))
        score = score_attempt(key.case, attempt)
        attempt_id = await insert_attempt(
            conn,
            case_id=key.case_id,
            attempt=attempt,
            score=score,
            option_ids=key.option_ids,
            is_simulated=simulated_label is not None,
            simulated_label=simulated_label,
        )
    return RecordedAttempt(attempt_id, key.case_id, key.slug, key.case, score)


async def cohort_stats(
    conn: AsyncConnection, *, case_id: int, attempt_id: int, max_points: int
) -> CohortStats:
    params = {"case_id": case_id, "attempt_id": attempt_id}
    row = (await conn.execute(sql("cohort_stats"), params)).one()
    size = int(row.cohort_size)
    percentile: float | None = None
    if size >= MIN_COHORT_FOR_PERCENTILE and row.percent_rank is not None:
        percentile = round(float(row.percent_rank) * 100, 1)
    bins = await conn.execute(sql("histogram"), {"case_id": case_id, "max_points": max_points})
    return CohortStats(
        percentile=percentile,
        cohort_size=size,
        cohort_is_simulated=bool(row.cohort_is_simulated),
        histogram=[HistogramBin(points=int(b.points), count=int(b.n)) for b in bins],
    )


async def pick_rates(conn: AsyncConnection, case_id: int) -> dict[tuple[str, str], float]:
    rows = await conn.execute(sql("pick_rates"), {"case_id": case_id})
    return {(r.stage, r.option_key): float(r.pick_rate) for r in rows}


def provider_of(model: str) -> str:
    """`claude-opus-4-8` -> `claude`, `gemini-3.8-flash` -> `gemini` (labels carry the model)."""
    return model.split("-", 1)[0]


async def benchmarks(conn: AsyncConnection, case_id: int) -> list[Benchmark]:
    rows = await conn.execute(sql("benchmarks"), {"case_id": case_id})
    out: list[Benchmark] = []
    for r in rows:
        model = str(r.label).removeprefix(AI_LABEL_PREFIX)
        out.append(
            Benchmark(
                label=r.label,
                provider=provider_of(model),
                model=model,
                points=r.points,
                max_points=r.max_points,
                diagnosis_correct=r.diagnosis_correct,
                confidence=r.confidence,
                calibration=calibrate(r.confidence, r.diagnosis_correct),
            )
        )
    return out


async def attempt_result(conn: AsyncConnection, recorded: RecordedAttempt) -> AttemptResult:
    """The debrief: run after `record_attempt` committed, so the attempt is in its own cohort."""
    stats = await cohort_stats(
        conn,
        case_id=recorded.case_id,
        attempt_id=recorded.attempt_id,
        max_points=recorded.score.max_points,
    )
    return build_attempt_result(
        case=recorded.case,
        slug=recorded.slug,
        attempt_id=recorded.attempt_id,
        score=recorded.score,
        stats=stats,
        pick_rates=await pick_rates(conn, recorded.case_id),
        benchmarks=await benchmarks(conn, recorded.case_id),
    )
