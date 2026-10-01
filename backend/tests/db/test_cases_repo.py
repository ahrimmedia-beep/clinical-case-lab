from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.repository.cases import (
    get_case_public,
    insert_case,
    list_cases,
    load_case,
    load_stored_case,
)
from app.schemas.case import ClinicalCase

pytestmark = pytest.mark.db

COUNTS_SQL = text(
    "SELECT (SELECT count(*) FROM cases) AS cases, "
    "(SELECT count(*) FROM case_findings) AS findings, "
    "(SELECT count(*) FROM case_measurements) AS measurements, "
    "(SELECT count(*) FROM case_diagnoses) AS diagnoses, "
    "(SELECT count(*) FROM case_decisions) AS decisions, "
    "(SELECT count(*) FROM decision_options) AS options, "
    "(SELECT count(*) FROM decision_accepted_answers) AS accepted"
)
PE_COUNTS = {
    "cases": 1,
    "findings": 5,
    "measurements": 3,
    "diagnoses": 2,
    "decisions": 5,
    "options": 12,
    "accepted": 3,
}


async def row_counts(conn: AsyncConnection) -> dict[str, int]:
    row = (await conn.execute(COUNTS_SQL)).mappings().one()
    await conn.rollback()
    return dict(row)


async def test_insert_is_idempotent(conn: AsyncConnection, case_pe: dict[str, Any]) -> None:
    case = ClinicalCase.model_validate(case_pe)
    first = await insert_case(conn, case)
    assert first.created is True
    assert first.slug.startswith("sudden-breathlessness-after-a-long-flight-")
    assert await row_counts(conn) == PE_COUNTS
    second = await insert_case(conn, case)
    assert (second.id, second.slug, second.created) == (first.id, first.slug, False)
    assert await row_counts(conn) == PE_COUNTS


async def test_load_case_round_trips_the_full_case(
    conn: AsyncConnection, case_pe: dict[str, Any]
) -> None:
    case = ClinicalCase.model_validate(case_pe)
    created = await insert_case(conn, case)
    loaded = await load_case(conn, created.slug)
    assert loaded is not None
    case_id, stored = loaded
    assert case_id == created.id
    assert stored == case
    assert await load_case(conn, "no-such-case") is None


async def test_public_view_hides_answers(conn: AsyncConnection, case_pe: dict[str, Any]) -> None:
    created = await insert_case(conn, ClinicalCase.model_validate(case_pe))
    public = await get_case_public(conn, created.slug)
    assert public is not None
    assert public.id == created.id and len(public.stages) == 9
    dumped = public.model_dump_json()
    assert '"is_correct"' not in dumped and "Thrombolysis is reserved" not in dumped
    assert await get_case_public(conn, "no-such-case") is None


async def test_list_cases_summarises(conn: AsyncConnection, case_pe: dict[str, Any]) -> None:
    created = await insert_case(conn, ClinicalCase.model_validate(case_pe))
    summaries = await list_cases(conn)
    assert [s.slug for s in summaries] == [created.slug]
    summary = summaries[0]
    assert (summary.decision_count, summary.attempts_count) == (5, 0)
    assert summary.source_kind == "manual"
    assert summary.patient.age_years == 34
    assert summary.review_status == "approved"


SOURCE_TEXT = "A 34-year-old woman presents with sudden breathlessness after a long flight."


def llm_case(case_pe: dict[str, Any]) -> ClinicalCase:
    source = {
        "kind": "llm",
        "provider": "gemini",
        "model": "gemini-3.8-flash",
        "prompt_version": "v1",
        "text": SOURCE_TEXT,
    }
    return ClinicalCase.model_validate({**case_pe, "source": source})


async def test_llm_case_is_stored_as_a_draft_with_its_source_text(
    conn: AsyncConnection, case_pe: dict[str, Any]
) -> None:
    created = await insert_case(conn, llm_case(case_pe))
    stored = await load_stored_case(conn, created.slug)
    assert stored is not None
    assert (stored.id, stored.slug) == (created.id, created.slug)
    assert stored.review_status == "draft" and stored.reviewed_at is None
    assert stored.case.source is not None
    assert stored.case.source.text == SOURCE_TEXT
    assert stored.case.source.model == "gemini-3.8-flash"
    public = await get_case_public(conn, created.slug)
    assert public is not None and public.review_status == "draft"
    assert SOURCE_TEXT not in public.model_dump_json()


async def test_manual_case_is_approved_on_ingest(
    conn: AsyncConnection, case_pe: dict[str, Any]
) -> None:
    created = await insert_case(conn, ClinicalCase.model_validate(case_pe))
    stored = await load_stored_case(conn, created.slug)
    assert stored is not None and stored.review_status == "approved"
    assert await load_stored_case(conn, "no-such-case") is None


async def test_public_view_uses_the_stored_review_status(
    conn: AsyncConnection, case_pe: dict[str, Any]
) -> None:
    created = await insert_case(conn, llm_case(case_pe))
    await conn.execute(
        text("UPDATE cases SET review_status = 'approved', reviewed_at = now() WHERE id = :id"),
        {"id": created.id},
    )
    public = await get_case_public(conn, created.slug)
    assert public is not None and public.review_status == "approved"


async def test_list_cases_puts_approved_cases_before_drafts(
    conn: AsyncConnection, case_pe: dict[str, Any]
) -> None:
    manual = await insert_case(conn, ClinicalCase.model_validate(case_pe))
    draft_data = {**case_pe, "estimated_minutes": 9}  # different content, so a new case
    draft = await insert_case(conn, llm_case(draft_data))
    summaries = await list_cases(conn)
    assert [(s.slug, s.review_status) for s in summaries] == [
        (manual.slug, "approved"),
        (draft.slug, "draft"),
    ]
    assert summaries[1].source_kind == "llm"


async def test_approved_llm_cases_stay_behind_the_curated_showcase(
    conn: AsyncConnection, case_pe: dict[str, Any]
) -> None:
    curated = await insert_case(conn, ClinicalCase.model_validate(case_pe))
    newer = await insert_case(conn, llm_case({**case_pe, "estimated_minutes": 11}))
    await conn.execute(
        text("UPDATE cases SET review_status = 'approved', reviewed_at = now() WHERE id = :id"),
        {"id": newer.id},
    )
    summaries = await list_cases(conn)
    # A studio case approved later must not push the hand-authored hero off the top.
    assert [s.slug for s in summaries] == [curated.slug, newer.slug]
