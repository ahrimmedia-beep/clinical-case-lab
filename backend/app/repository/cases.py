"""Case aggregate: idempotent ingest (Core inserts, one transaction) and SQL-file reads."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, Text, insert, literal_column
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection

from app.case_views import build_case_public, default_review_status
from app.db.queries import sql
from app.db.tables import (
    case_decisions,
    case_diagnoses,
    case_findings,
    case_measurements,
    cases,
    decision_accepted_answers,
    decision_options,
)
from app.schemas.case import (
    CaseCreated,
    CasePublic,
    CaseSource,
    CaseSummary,
    ClinicalCase,
    Patient,
    ReviewStatus,
    SourceKind,
)
from app.textnorm import normalize


@dataclass(frozen=True)
class StoredCase:
    """A case as stored, answer key and source text included. Server-side only."""

    id: int
    slug: str
    case: ClinicalCase
    review_status: ReviewStatus
    reviewed_at: datetime | None


def canonical_json(case: ClinicalCase) -> str:
    payload = case.model_dump(mode="json", exclude={"source"})
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def content_hash(case: ClinicalCase) -> str:
    return hashlib.sha256(canonical_json(case).encode("utf-8")).hexdigest()


def make_slug(title: str, digest: str) -> str:
    base = normalize(title).replace(" ", "-")[:80].strip("-") or "case"
    return f"{base}-{digest[:6]}"


async def insert_case(conn: AsyncConnection, case: ClinicalCase) -> CaseCreated:
    """Insert a case and its children in one transaction; an identical case is a no-op.

    `ON CONFLICT ... DO UPDATE` (not DO NOTHING) so RETURNING always yields the row;
    `xmax = 0` is true only for a freshly inserted tuple. LLM-authored cases are stored as
    `draft` with their de-identified source text (for the review page); others as `approved`.
    """
    digest = content_hash(case)
    source = case.source or CaseSource(kind=SourceKind.MANUAL)
    base = pg_insert(cases).values(
        slug=make_slug(case.title, digest),
        schema_version=case.schema_version,
        title=case.title,
        specialty=case.specialty,
        difficulty=case.difficulty.value,
        estimated_minutes=case.estimated_minutes,
        patient_display_name=case.patient.display_name,
        patient_age=case.patient.age_years,
        patient_sex=case.patient.sex.value,
        chief_complaint=case.chief_complaint,
        vignette=case.vignette,
        source_kind=source.kind.value,
        source_provider=source.provider,
        source_model=source.model,
        prompt_version=source.prompt_version,
        source_text=source.text,
        review_status=default_review_status(case).value,
        content_hash=digest,
    )
    upsert = base.on_conflict_do_update(
        index_elements=[cases.c.content_hash],
        set_={"content_hash": base.excluded.content_hash},
    ).returning(
        cases.c.id,
        cases.c.slug,
        literal_column("(xmax = 0)", Boolean).label("inserted"),
    )
    async with conn.begin():
        row = (await conn.execute(upsert)).one()
        if row.inserted:
            await _insert_children(conn, row.id, case)
    return CaseCreated(id=row.id, slug=row.slug, created=bool(row.inserted))


async def _insert_children(conn: AsyncConnection, case_id: int, case: ClinicalCase) -> None:
    if case.findings:
        await conn.execute(
            insert(case_findings),
            [
                {
                    "case_id": case_id,
                    "position": i,
                    "category": f.category.value,
                    "text": f.text,
                    "evidence": f.evidence,
                }
                for i, f in enumerate(case.findings)
            ],
        )
    if case.measurements:
        await conn.execute(
            insert(case_measurements),
            [
                {
                    "case_id": case_id,
                    "position": i,
                    "kind": m.kind.value,
                    "name": m.name,
                    "value": None if m.value is None else Decimal(str(m.value)),
                    "value_text": m.value_text,
                    "unit": m.unit,
                    "flag": m.flag.value if m.flag else None,
                    "evidence": m.evidence,
                }
                for i, m in enumerate(case.measurements)
            ],
        )
    diagnoses: list[dict[str, Any]] = [
        {
            "case_id": case_id,
            "role": "final",
            "position": 0,
            "name": case.final_diagnosis.name,
            "icd10": case.final_diagnosis.icd10,
            "evidence": case.final_diagnosis.evidence,
        }
    ]
    diagnoses += [
        {
            "case_id": case_id,
            "role": "differential",
            "position": i,
            "name": d.name,
            "icd10": d.icd10,
            "evidence": d.evidence,
        }
        for i, d in enumerate(case.differential)
    ]
    await conn.execute(insert(case_diagnoses), diagnoses)
    for decision in case.decisions:  # at most five, so one round trip each is fine
        decision_id = await conn.scalar(
            insert(case_decisions)
            .values(
                case_id=case_id,
                stage=decision.stage.value,
                prompt=decision.prompt,
                explanation=decision.explanation,
            )
            .returning(case_decisions.c.id)
        )
        if decision.options:
            await conn.execute(
                insert(decision_options),
                [
                    {
                        "decision_id": decision_id,
                        "position": i,
                        "key": o.key,
                        "text": o.text,
                        "is_correct": o.is_correct,
                        "is_harmful": o.is_harmful,
                        "feedback": o.feedback,
                        "reveal": o.reveal,
                    }
                    for i, o in enumerate(decision.options)
                ],
            )
        if decision.accepted_answers:
            await conn.execute(
                insert(decision_accepted_answers),
                [{"decision_id": decision_id, "text": a} for a in decision.accepted_answers],
            )


async def load_stored_case(conn: AsyncConnection, slug: str) -> StoredCase | None:
    """The full case with its answer key, review state and source text, in one query."""
    stmt = sql("case_document").columns(
        id=BigInteger, slug=Text, review_status=Text, reviewed_at=DateTime(timezone=True), doc=JSONB
    )
    row = (await conn.execute(stmt, {"slug": slug})).one_or_none()
    if row is None:
        return None
    return StoredCase(
        id=int(row.id),
        slug=row.slug,
        case=ClinicalCase.model_validate(row.doc),
        review_status=ReviewStatus(row.review_status),
        reviewed_at=row.reviewed_at,
    )


async def load_case(conn: AsyncConnection, slug: str) -> tuple[int, ClinicalCase] | None:
    """The full case with its answer key. Never return this to a client."""
    stored = await load_stored_case(conn, slug)
    return None if stored is None else (stored.id, stored.case)


async def get_case_public(conn: AsyncConnection, slug: str) -> CasePublic | None:
    stored = await load_stored_case(conn, slug)
    if stored is None:
        return None
    return build_case_public(stored.id, slug, stored.case, review_status=stored.review_status)


async def list_cases(conn: AsyncConnection) -> list[CaseSummary]:
    rows = (await conn.execute(sql("list_cases"))).mappings().all()
    return [
        CaseSummary(
            id=r["id"],
            slug=r["slug"],
            title=r["title"],
            specialty=r["specialty"],
            difficulty=r["difficulty"],
            estimated_minutes=r["estimated_minutes"],
            patient=Patient(
                display_name=r["patient_display_name"],
                age_years=r["patient_age"],
                sex=r["patient_sex"],
            ),
            chief_complaint=r["chief_complaint"],
            decision_count=r["decision_count"],
            attempts_count=r["attempts_count"],
            source_kind=r["source_kind"],
            review_status=r["review_status"],
            created_at=r["created_at"],
        )
        for r in rows
    ]
