"""PostgreSQL schema as SQLAlchemy Core tables: the single source for Alembic autogenerate."""

from __future__ import annotations

from sqlalchemy import (
    CHAR,
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    MetaData,
    Numeric,
    PrimaryKeyConstraint,
    SmallInteger,
    Table,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.schemas.case import (
    Difficulty,
    FindingCategory,
    Flag,
    MeasurementKind,
    ReviewStatus,
    Sex,
    SourceKind,
)
from app.stages import DecisionStage

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)


def _one_of(column: str, values: list[str], *, nullable: bool = False) -> str:
    listed = ", ".join(f"'{v}'" for v in values)
    clause = f"{column} IN ({listed})"
    return f"{column} IS NULL OR {clause}" if nullable else clause


def _id() -> Column[int]:
    return Column("id", BigInteger, Identity(), primary_key=True)


def _fk(name: str, target: str) -> Column[int]:
    return Column(name, BigInteger, ForeignKey(target, ondelete="CASCADE"), nullable=False)


cases = Table(
    "cases",
    metadata,
    _id(),
    Column("slug", Text, nullable=False),
    Column("schema_version", Text, nullable=False),
    Column("title", Text, nullable=False),
    Column("specialty", Text, nullable=False),
    Column("difficulty", Text, nullable=False),
    Column("estimated_minutes", SmallInteger, nullable=False),
    Column("patient_display_name", Text),
    Column("patient_age", SmallInteger),
    Column("patient_sex", Text, nullable=False),
    Column("chief_complaint", Text, nullable=False),
    Column("vignette", Text, nullable=False),
    Column("source_kind", Text, nullable=False),
    Column("source_provider", Text),
    Column("source_model", Text),
    Column("prompt_version", Text),
    Column("source_text", Text),
    Column("review_status", Text, nullable=False),
    Column("reviewed_at", DateTime(timezone=True)),
    Column("content_hash", CHAR(64), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("slug", name="uq_cases_slug"),
    UniqueConstraint("content_hash", name="uq_cases_content_hash"),
    CheckConstraint(_one_of("difficulty", [d.value for d in Difficulty]), name="difficulty"),
    CheckConstraint("estimated_minutes BETWEEN 3 AND 30", name="estimated_minutes"),
    CheckConstraint("patient_age IS NULL OR patient_age BETWEEN 0 AND 120", name="patient_age"),
    CheckConstraint(_one_of("patient_sex", [s.value for s in Sex]), name="patient_sex"),
    CheckConstraint(_one_of("source_kind", [s.value for s in SourceKind]), name="source_kind"),
    CheckConstraint(
        _one_of("review_status", [s.value for s in ReviewStatus]), name="review_status"
    ),
)

case_findings = Table(
    "case_findings",
    metadata,
    _id(),
    _fk("case_id", "cases.id"),
    Column("position", SmallInteger, nullable=False),
    Column("category", Text, nullable=False),
    Column("text", Text, nullable=False),
    Column("evidence", Text),
    CheckConstraint(_one_of("category", [c.value for c in FindingCategory]), name="category"),
    Index("ix_case_findings_case_id", "case_id"),
)

case_measurements = Table(
    "case_measurements",
    metadata,
    _id(),
    _fk("case_id", "cases.id"),
    Column("position", SmallInteger, nullable=False),
    Column("kind", Text, nullable=False),
    Column("name", Text, nullable=False),
    Column("value", Numeric),
    Column("value_text", Text),
    Column("unit", Text),
    Column("flag", Text),
    Column("evidence", Text),
    CheckConstraint(_one_of("kind", [k.value for k in MeasurementKind]), name="kind"),
    CheckConstraint(_one_of("flag", [f.value for f in Flag], nullable=True), name="flag"),
    Index("ix_case_measurements_case_id", "case_id"),
)

case_diagnoses = Table(
    "case_diagnoses",
    metadata,
    _id(),
    _fk("case_id", "cases.id"),
    Column("role", Text, nullable=False),
    Column("position", SmallInteger, nullable=False),
    Column("name", Text, nullable=False),
    Column("icd10", Text),
    Column("evidence", Text),
    CheckConstraint(_one_of("role", ["final", "differential"]), name="role"),
    Index("ix_case_diagnoses_case_id", "case_id"),
    Index(
        "uq_case_diagnoses_final",
        "case_id",
        unique=True,
        postgresql_where=text("role = 'final'"),
    ),
)

case_decisions = Table(
    "case_decisions",
    metadata,
    _id(),
    _fk("case_id", "cases.id"),
    Column("stage", Text, nullable=False),
    Column("prompt", Text, nullable=False),
    Column("explanation", Text, nullable=False),
    UniqueConstraint("case_id", "stage", name="uq_case_decisions_case_id_stage"),
    CheckConstraint(_one_of("stage", [s.value for s in DecisionStage]), name="stage"),
)

decision_options = Table(
    "decision_options",
    metadata,
    _id(),
    _fk("decision_id", "case_decisions.id"),
    Column("position", SmallInteger, nullable=False),
    Column("key", Text, nullable=False),
    Column("text", Text, nullable=False),
    Column("is_correct", Boolean, nullable=False),
    Column("is_harmful", Boolean, nullable=False),
    Column("feedback", Text),
    Column("reveal", Text),
    UniqueConstraint("decision_id", "key", name="uq_decision_options_decision_id_key"),
    CheckConstraint("NOT (is_correct AND is_harmful)", name="not_correct_and_harmful"),
)

decision_accepted_answers = Table(
    "decision_accepted_answers",
    metadata,
    _id(),
    _fk("decision_id", "case_decisions.id"),
    Column("text", Text, nullable=False),
    Index("ix_decision_accepted_answers_decision_id", "decision_id"),
)

attempts = Table(
    "attempts",
    metadata,
    _id(),
    _fk("case_id", "cases.id"),
    Column("points", SmallInteger, nullable=False),
    Column("max_points", SmallInteger, nullable=False),
    Column("right_count", SmallInteger, nullable=False),
    Column("wrong_count", SmallInteger, nullable=False),
    Column("missed_count", SmallInteger, nullable=False),
    Column("harmful_count", SmallInteger, nullable=False),
    Column("diagnosis_text", Text, nullable=False),
    Column("diagnosis_correct", Boolean, nullable=False),
    Column("confidence", SmallInteger, nullable=False),
    Column("duration_ms", Integer),
    Column("is_simulated", Boolean, nullable=False, server_default=text("false")),
    Column("simulated_label", Text),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    CheckConstraint("confidence BETWEEN 1 AND 5", name="confidence"),
    Index("ix_attempts_case_id_points", "case_id", "points"),
)

attempt_choices = Table(
    "attempt_choices",
    metadata,
    Column("attempt_id", BigInteger, ForeignKey("attempts.id", ondelete="CASCADE"), nullable=False),
    Column(
        "option_id",
        BigInteger,
        ForeignKey("decision_options.id", ondelete="CASCADE"),
        nullable=False,
    ),
    PrimaryKeyConstraint("attempt_id", "option_id"),
    Index("ix_attempt_choices_option_id", "option_id"),
)

# POST /api/extract result cache (pipeline/cache.py's in-memory LRU, persisted): survives a
# Cloud Run instance restart. key = sha256(text, provider, model, PROMPT_VERSION); response is
# the full ExtractResponse JSON exactly as first returned.
extract_cache = Table(
    "extract_cache",
    metadata,
    Column("key", CHAR(64), primary_key=True),
    Column("provider", Text),
    Column("model", Text),
    Column("prompt_version", Text),
    Column("response", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

# Daily budgets that must survive an instance restart (Cloud Run scales to zero): one row per UTC
# day and kind. kind = 'extract' counts paid /api/extract runs, failed ones included; a slot is
# reserved with a conditional upsert before the model is called (app.repository.extract_cache).
daily_usage = Table(
    "daily_usage",
    metadata,
    Column("day", Date, nullable=False),
    Column("kind", Text, nullable=False),
    Column("count", Integer, nullable=False),
    PrimaryKeyConstraint("day", "kind"),
    CheckConstraint("count >= 0", name="count"),
)
