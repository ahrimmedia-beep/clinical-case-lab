"""The clinical case contract (schema_version 1.0). Single source of truth for API, LLM and web."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import StrictModel
from app.stages import MULTI_SELECT_STAGES, REVEAL_STAGES, DecisionStage, Stage
from app.textnorm import contains_term, normalize


class Sex(StrEnum):
    FEMALE = "female"
    MALE = "male"
    OTHER = "other"
    UNKNOWN = "unknown"


class Difficulty(StrEnum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class FindingCategory(StrEnum):
    SYMPTOM = "symptom"
    HISTORY = "history"
    MEDICATION = "medication"
    ALLERGY = "allergy"
    SOCIAL = "social"
    FAMILY = "family"
    EXAM = "exam"
    IMAGING = "imaging"
    PROCEDURE = "procedure"


class MeasurementKind(StrEnum):
    VITAL = "vital"
    LAB = "lab"


class Flag(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    ABNORMAL = "abnormal"


class SourceKind(StrEnum):
    MANUAL = "manual"
    LLM = "llm"


# Which facts are shown on which "given" stage of the player.
GIVEN_STAGE_CATEGORIES: dict[Stage, set[str]] = {
    Stage.HISTORY: {"symptom", "history", "medication", "allergy", "social", "family"},
    Stage.EXAMINATION: {"exam", "vital"},
    Stage.RESULTS: {"imaging", "procedure", "lab"},
}


class Patient(StrictModel):
    display_name: str | None = Field(default=None, max_length=60)
    age_years: int | None = Field(default=None, ge=0, le=120)
    sex: Sex = Sex.UNKNOWN


class Finding(StrictModel):
    category: FindingCategory
    text: str = Field(min_length=1, max_length=400)
    evidence: str | None = Field(default=None, max_length=600)


class Measurement(StrictModel):
    kind: MeasurementKind
    name: str = Field(min_length=1, max_length=80)
    value: float | None = None
    value_text: str | None = Field(default=None, max_length=120)
    unit: str | None = Field(default=None, max_length=30)
    flag: Flag | None = None
    evidence: str | None = Field(default=None, max_length=600)

    @model_validator(mode="after")
    def _has_a_value(self) -> Measurement:
        if self.value is None and not self.value_text:
            raise ValueError("measurement needs value or value_text")
        return self


class Diagnosis(StrictModel):
    name: str = Field(min_length=2, max_length=160)
    icd10: str | None = Field(default=None, pattern=r"^[A-Z][0-9][0-9A-Z](\.[0-9A-Z]{1,4})?$")
    evidence: str | None = Field(default=None, max_length=600)


class Option(StrictModel):
    key: str = Field(pattern=r"^[A-L]$")
    text: str = Field(min_length=1, max_length=200)
    is_correct: bool
    is_harmful: bool = False
    feedback: str | None = Field(default=None, max_length=400)
    reveal: str | None = Field(default=None, max_length=400)

    @model_validator(mode="after")
    def _harmful_is_not_correct(self) -> Option:
        if self.is_harmful and self.is_correct:
            raise ValueError("a harmful option cannot be correct")
        return self


class Decision(StrictModel):
    stage: DecisionStage
    prompt: str = Field(min_length=3, max_length=300)
    explanation: str = Field(min_length=1, max_length=1200)
    options: list[Option] = Field(default_factory=list, max_length=12)
    accepted_answers: list[str] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def _shape_matches_stage(self) -> Decision:
        stage = Stage(self.stage)
        if stage is Stage.DIAGNOSIS:
            if self.options:
                raise ValueError("the diagnosis decision is free-text and has no options")
            if not self.accepted_answers:
                raise ValueError("the diagnosis decision needs at least one accepted answer")
            return self
        if stage in MULTI_SELECT_STAGES:
            if not 3 <= len(self.options) <= 12:
                raise ValueError(f"{stage} needs 3 to 12 options")
            if len({o.key for o in self.options}) != len(self.options):
                raise ValueError("option keys must be unique within a decision")
            if not any(o.is_correct for o in self.options):
                raise ValueError(f"{stage} needs at least one correct option")
            if self.accepted_answers:
                raise ValueError("accepted_answers only apply to the diagnosis decision")
            if stage not in REVEAL_STAGES and any(o.reveal for o in self.options):
                raise ValueError("reveal is only allowed on interview and workup options")
        return self


class CaseSource(StrictModel):
    kind: SourceKind
    provider: str | None = Field(default=None, max_length=40)
    model: str | None = Field(default=None, max_length=80)
    prompt_version: str | None = Field(default=None, max_length=40)


class ClinicalCase(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    title: str = Field(min_length=3, max_length=120)
    specialty: str = Field(min_length=2, max_length=60)
    difficulty: Difficulty
    estimated_minutes: int = Field(ge=3, le=30)
    patient: Patient
    chief_complaint: str = Field(min_length=3, max_length=300)
    vignette: str = Field(min_length=20, max_length=3000)
    findings: list[Finding] = Field(default_factory=list, max_length=80)
    measurements: list[Measurement] = Field(default_factory=list, max_length=80)
    final_diagnosis: Diagnosis
    differential: list[Diagnosis] = Field(default_factory=list, max_length=12)
    decisions: list[Decision] = Field(min_length=1, max_length=5)
    source: CaseSource | None = None

    def diagnosis_terms(self) -> list[str]:
        terms: list[str] = [self.final_diagnosis.name]
        for decision in self.decisions:
            if decision.stage == DecisionStage.DIAGNOSIS:
                terms.extend(decision.accepted_answers)
        seen: set[str] = set()
        unique: list[str] = []
        for term in terms:
            key = normalize(term)
            if key and key not in seen:
                seen.add(key)
                unique.append(term)
        return unique

    @model_validator(mode="after")
    def _case_rules(self) -> ClinicalCase:
        stages = [d.stage for d in self.decisions]
        if len(stages) != len(set(stages)):
            raise ValueError("one decision per stage")
        if DecisionStage.DIAGNOSIS not in stages:
            raise ValueError("a diagnosis decision is required")
        exposed = {
            "title": self.title,
            "vignette": self.vignette,
            "chief_complaint": self.chief_complaint,
        }
        for d in self.decisions:
            exposed[f"decisions[{d.stage}].prompt"] = d.prompt
        for term in self.diagnosis_terms():
            for where, text in exposed.items():
                if contains_term(text, term):
                    raise ValueError(f"{where} leaks the diagnosis ({term!r})")
        return self


# ---------- read models (what the browser may see) ----------


class PublicOption(BaseModel):
    key: str
    text: str


class StageItem(BaseModel):
    kind: Literal["finding", "measurement"]
    category: str
    text: str
    value: str | None = None
    unit: str | None = None
    flag: Flag | None = None
    withheld: bool = False


class PublicStage(BaseModel):
    number: int
    key: Stage
    label: str
    hint: str
    kind: Literal["given", "decision"]
    scored: bool
    items: list[StageItem] = Field(default_factory=list)
    prompt: str | None = None
    input: Literal["multi_select", "free_text"] | None = None
    options: list[PublicOption] = Field(default_factory=list)


class CasePublic(BaseModel):
    id: int
    slug: str
    title: str
    specialty: str
    difficulty: Difficulty
    estimated_minutes: int
    patient: Patient
    chief_complaint: str
    vignette: str
    source_kind: SourceKind
    stages: list[PublicStage]


class CaseSummary(BaseModel):
    id: int
    slug: str
    title: str
    specialty: str
    difficulty: Difficulty
    estimated_minutes: int
    patient: Patient
    chief_complaint: str
    decision_count: int
    attempts_count: int
    source_kind: SourceKind
    created_at: datetime


class CaseCreated(BaseModel):
    id: int
    slug: str
    created: bool
