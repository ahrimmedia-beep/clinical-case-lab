"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-01

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _id() -> sa.Column[int]:
    return sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False)


def _fk(column: str, table: str, target: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [column],
        [f"{target}.id"],
        name=op.f(f"fk_{table}_{column}_{target}"),
        ondelete="CASCADE",
    )


def upgrade() -> None:
    op.create_table(
        "cases",
        _id(),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("schema_version", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("specialty", sa.Text(), nullable=False),
        sa.Column("difficulty", sa.Text(), nullable=False),
        sa.Column("estimated_minutes", sa.SmallInteger(), nullable=False),
        sa.Column("patient_display_name", sa.Text(), nullable=True),
        sa.Column("patient_age", sa.SmallInteger(), nullable=True),
        sa.Column("patient_sex", sa.Text(), nullable=False),
        sa.Column("chief_complaint", sa.Text(), nullable=False),
        sa.Column("vignette", sa.Text(), nullable=False),
        sa.Column("source_kind", sa.Text(), nullable=False),
        sa.Column("source_provider", sa.Text(), nullable=True),
        sa.Column("source_model", sa.Text(), nullable=True),
        sa.Column("prompt_version", sa.Text(), nullable=True),
        sa.Column("source_text", sa.Text(), nullable=True),
        sa.Column("review_status", sa.Text(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("content_hash", sa.CHAR(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "difficulty IN ('easy', 'medium', 'hard')", name=op.f("ck_cases_difficulty")
        ),
        sa.CheckConstraint(
            "estimated_minutes BETWEEN 3 AND 30", name=op.f("ck_cases_estimated_minutes")
        ),
        sa.CheckConstraint(
            "patient_age IS NULL OR patient_age BETWEEN 0 AND 120",
            name=op.f("ck_cases_patient_age"),
        ),
        sa.CheckConstraint(
            "patient_sex IN ('female', 'male', 'other', 'unknown')",
            name=op.f("ck_cases_patient_sex"),
        ),
        sa.CheckConstraint("source_kind IN ('manual', 'llm')", name=op.f("ck_cases_source_kind")),
        sa.CheckConstraint(
            "review_status IN ('draft', 'approved')", name=op.f("ck_cases_review_status")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cases")),
        sa.UniqueConstraint("content_hash", name="uq_cases_content_hash"),
        sa.UniqueConstraint("slug", name="uq_cases_slug"),
    )
    op.create_table(
        "case_findings",
        _id(),
        sa.Column("case_id", sa.BigInteger(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "category IN ('symptom', 'history', 'medication', 'allergy', 'social', 'family', "
            "'exam', 'imaging', 'procedure')",
            name=op.f("ck_case_findings_category"),
        ),
        _fk("case_id", "case_findings", "cases"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_case_findings")),
    )
    op.create_index("ix_case_findings_case_id", "case_findings", ["case_id"])
    op.create_table(
        "case_measurements",
        _id(),
        sa.Column("case_id", sa.BigInteger(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("value", sa.Numeric(), nullable=True),
        sa.Column("value_text", sa.Text(), nullable=True),
        sa.Column("unit", sa.Text(), nullable=True),
        sa.Column("flag", sa.Text(), nullable=True),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.CheckConstraint("kind IN ('vital', 'lab')", name=op.f("ck_case_measurements_kind")),
        sa.CheckConstraint(
            "flag IS NULL OR flag IN ('low', 'normal', 'high', 'abnormal')",
            name=op.f("ck_case_measurements_flag"),
        ),
        _fk("case_id", "case_measurements", "cases"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_case_measurements")),
    )
    op.create_index("ix_case_measurements_case_id", "case_measurements", ["case_id"])
    op.create_table(
        "case_diagnoses",
        _id(),
        sa.Column("case_id", sa.BigInteger(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("icd10", sa.Text(), nullable=True),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "role IN ('final', 'differential')", name=op.f("ck_case_diagnoses_role")
        ),
        _fk("case_id", "case_diagnoses", "cases"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_case_diagnoses")),
    )
    op.create_index("ix_case_diagnoses_case_id", "case_diagnoses", ["case_id"])
    op.create_index(
        "uq_case_diagnoses_final",
        "case_diagnoses",
        ["case_id"],
        unique=True,
        postgresql_where=sa.text("role = 'final'"),
    )
    op.create_table(
        "case_decisions",
        _id(),
        sa.Column("case_id", sa.BigInteger(), nullable=False),
        sa.Column("stage", sa.Text(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "stage IN ('interview', 'differential', 'workup', 'diagnosis', 'treatment')",
            name=op.f("ck_case_decisions_stage"),
        ),
        _fk("case_id", "case_decisions", "cases"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_case_decisions")),
        sa.UniqueConstraint("case_id", "stage", name="uq_case_decisions_case_id_stage"),
    )
    op.create_table(
        "decision_options",
        _id(),
        sa.Column("decision_id", sa.BigInteger(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.Column("is_harmful", sa.Boolean(), nullable=False),
        sa.Column("feedback", sa.Text(), nullable=True),
        sa.Column("reveal", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "NOT (is_correct AND is_harmful)",
            name=op.f("ck_decision_options_not_correct_and_harmful"),
        ),
        _fk("decision_id", "decision_options", "case_decisions"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_decision_options")),
        sa.UniqueConstraint("decision_id", "key", name="uq_decision_options_decision_id_key"),
    )
    op.create_table(
        "decision_accepted_answers",
        _id(),
        sa.Column("decision_id", sa.BigInteger(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        _fk("decision_id", "decision_accepted_answers", "case_decisions"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_decision_accepted_answers")),
    )
    op.create_index(
        "ix_decision_accepted_answers_decision_id",
        "decision_accepted_answers",
        ["decision_id"],
    )
    op.create_table(
        "attempts",
        _id(),
        sa.Column("case_id", sa.BigInteger(), nullable=False),
        sa.Column("points", sa.SmallInteger(), nullable=False),
        sa.Column("max_points", sa.SmallInteger(), nullable=False),
        sa.Column("right_count", sa.SmallInteger(), nullable=False),
        sa.Column("wrong_count", sa.SmallInteger(), nullable=False),
        sa.Column("missed_count", sa.SmallInteger(), nullable=False),
        sa.Column("harmful_count", sa.SmallInteger(), nullable=False),
        sa.Column("diagnosis_text", sa.Text(), nullable=False),
        sa.Column("diagnosis_correct", sa.Boolean(), nullable=False),
        sa.Column("confidence", sa.SmallInteger(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("is_simulated", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("simulated_label", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("confidence BETWEEN 1 AND 5", name=op.f("ck_attempts_confidence")),
        _fk("case_id", "attempts", "cases"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_attempts")),
    )
    op.create_index("ix_attempts_case_id_points", "attempts", ["case_id", "points"])
    op.create_table(
        "attempt_choices",
        sa.Column("attempt_id", sa.BigInteger(), nullable=False),
        sa.Column("option_id", sa.BigInteger(), nullable=False),
        _fk("attempt_id", "attempt_choices", "attempts"),
        _fk("option_id", "attempt_choices", "decision_options"),
        sa.PrimaryKeyConstraint("attempt_id", "option_id", name=op.f("pk_attempt_choices")),
    )
    op.create_index("ix_attempt_choices_option_id", "attempt_choices", ["option_id"])


def downgrade() -> None:
    for table in (
        "attempt_choices",
        "attempts",
        "decision_accepted_answers",
        "decision_options",
        "case_decisions",
        "case_diagnoses",
        "case_measurements",
        "case_findings",
        "cases",
    ):
        op.drop_table(table)
