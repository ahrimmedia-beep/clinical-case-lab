"""★3 sponsor insights: one SQL query (`insights.sql`) shaped into `CaseInsights`."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable
from typing import Any

from sqlalchemy import BigInteger, Boolean, Float, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncConnection

from app.db.queries import sql
from app.repository.attempts import benchmarks
from app.schemas.insights import (
    CaseInsights,
    InsightOption,
    InsightStage,
    KeyTestEffect,
    MissedOption,
    WrongDiagnosis,
)
from app.scoring import normalize_diagnosis
from app.stages import CATALOGUE, MULTI_SELECT_STAGES, DecisionStage

TOP_WRONG_DIAGNOSES = 5


def merge_wrong_diagnoses(
    rows: Iterable[tuple[str, int]], *, limit: int = TOP_WRONG_DIAGNOSES
) -> list[WrongDiagnosis]:
    """Group wrong answers by the scorer's normalization ("COPD" = "chronic obstructive
    pulmonary disease"); each group is labelled with its most common spelling."""
    counts: Counter[str] = Counter()
    spellings: defaultdict[str, Counter[str]] = defaultdict(Counter)
    for text, count in rows:
        key = normalize_diagnosis(text)
        if not key:
            continue
        counts[key] += count
        spellings[key][text.strip()] += count
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]
    return [
        WrongDiagnosis(text=spellings[key].most_common(1)[0][0], count=count)
        for key, count in ranked
    ]


def _rate(part: int, whole: int) -> float:
    return part / whole if whole else 0.0


def _stages(options: list[dict[str, Any]], cohort_size: int) -> list[InsightStage]:
    by_stage: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for option in options:
        by_stage[option["stage"]].append(option)
    stages: list[InsightStage] = []
    for info in CATALOGUE:
        rows = by_stage.get(info.key.value)
        if info.key not in MULTI_SELECT_STAGES or not rows:
            continue
        picked = [
            InsightOption(
                key=r["key"],
                text=r["text"],
                is_correct=r["is_correct"],
                is_harmful=r["is_harmful"],
                pick_rate=_rate(r["picks"], cohort_size),
            )
            for r in rows
        ]
        missed = sorted(
            (
                MissedOption(key=o.key, text=o.text, missed_rate=1 - o.pick_rate)
                for o in picked
                if o.is_correct
            ),
            key=lambda m: -m.missed_rate,
        )
        stages.append(
            InsightStage(
                stage=DecisionStage(info.key.value),
                label=info.label,
                options=picked,
                missed_correct=missed if cohort_size else [],
            )
        )
    return stages


async def case_insights(conn: AsyncConnection, slug: str) -> CaseInsights | None:
    stmt = sql("insights").columns(
        id=BigInteger,
        slug=Text,
        title=Text,
        cohort_size=Integer,
        cohort_is_simulated=Boolean,
        dx_accuracy=Float,
        options=JSONB,
        wrong_dx=JSONB,
        key_tests=JSONB,
    )
    row = (await conn.execute(stmt, {"slug": slug})).one_or_none()
    if row is None:
        return None
    size = int(row.cohort_size)
    return CaseInsights(
        slug=row.slug,
        title=row.title,
        cohort_size=size,
        cohort_is_simulated=bool(row.cohort_is_simulated),
        diagnosis_accuracy=row.dx_accuracy,
        top_wrong_diagnoses=merge_wrong_diagnoses((w["text"], w["count"]) for w in row.wrong_dx),
        stages=_stages(row.options, size),
        key_tests=[
            KeyTestEffect(
                key=k["key"],
                text=k["text"],
                chose_rate=_rate(k["chose"], size),
                dx_accuracy_if_chosen=k["acc_chosen"],
                dx_accuracy_if_not=k["acc_not"],
            )
            for k in row.key_tests
        ],
        benchmarks=await benchmarks(conn, int(row.id)),
    )
