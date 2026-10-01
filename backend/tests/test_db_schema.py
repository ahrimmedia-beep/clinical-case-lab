from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.tables import metadata
from app.main import create_app

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
}


def test_metadata_has_exactly_the_spec_tables() -> None:
    assert set(metadata.tables) == SPEC_TABLES


def test_constraint_names_follow_the_convention() -> None:
    cases = metadata.tables["cases"]
    names = {c.name for c in cases.constraints}
    assert {"pk_cases", "uq_cases_slug", "uq_cases_content_hash", "ck_cases_difficulty"} <= names
    options = metadata.tables["decision_options"]
    assert "uq_decision_options_decision_id_key" in {c.name for c in options.constraints}
    diagnoses = metadata.tables["case_diagnoses"]
    partial = next(i for i in diagnoses.indexes if i.name == "uq_case_diagnoses_final")
    assert partial.unique


def test_lifespan_creates_the_engine_with_the_small_pool() -> None:
    app = create_app()
    with TestClient(app):  # runs the lifespan; no DB I/O happens until a request needs it
        engine = app.state.engine
        assert isinstance(engine, AsyncEngine)
        assert engine.pool.size() == 5  # type: ignore[attr-defined]


def test_cases_carry_the_review_gate_columns() -> None:
    cases = metadata.tables["cases"]
    assert cases.c.source_text.nullable
    assert not cases.c.review_status.nullable
    assert cases.c.reviewed_at.nullable
    assert cases.c.reviewed_at.type.timezone  # type: ignore[attr-defined]
    assert "ck_cases_review_status" in {c.name for c in cases.constraints}
