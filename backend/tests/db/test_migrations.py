from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.db.support import run_alembic

pytestmark = pytest.mark.db

SPEC_TABLES = {
    "cases",
    "case_findings",
    "case_measurements",
    "case_diagnoses",
    "case_decisions",
    "decision_options",
    "decision_accepted_answers",
    "attempts",
    "attempt_choices",
    "extract_cache",
    "daily_usage",
}
TABLES_SQL = text(
    "SELECT table_name FROM information_schema.tables "
    "WHERE table_schema = 'public' AND table_name <> 'alembic_version'"
)


async def _tables(engine: AsyncEngine) -> set[str]:
    async with engine.connect() as conn:
        return set((await conn.execute(TABLES_SQL)).scalars())


async def test_tables_and_migrations_do_not_drift(db_engine: AsyncEngine) -> None:
    result = run_alembic("check")
    assert "No new upgrade operations detected" in result.stdout + result.stderr


async def test_upgrade_downgrade_upgrade(db_engine: AsyncEngine) -> None:
    try:
        run_alembic("downgrade", "base")
        assert await _tables(db_engine) == set()
    finally:
        run_alembic("upgrade", "head")
    assert await _tables(db_engine) == SPEC_TABLES


async def test_review_status_check_rejects_unknown_values(engine: AsyncEngine) -> None:
    insert = text(
        "INSERT INTO cases (slug, schema_version, title, specialty, difficulty, "
        "estimated_minutes, patient_sex, chief_complaint, vignette, source_kind, "
        "review_status, content_hash) VALUES ('s-1', '1.0', 't', 'x', 'easy', 5, 'female', "
        "'c', 'v', 'manual', :status, repeat('a', 64))"
    )
    async with engine.connect() as conn:
        with pytest.raises(IntegrityError, match="ck_cases_review_status"):
            await conn.execute(insert, {"status": "published"})
