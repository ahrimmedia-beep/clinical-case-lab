"""Sponsor view: where the cohort goes wrong at each decision point."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.attempt import Benchmark
from app.stages import DecisionStage


class InsightOption(BaseModel):
    key: str
    text: str
    is_correct: bool
    is_harmful: bool
    pick_rate: float = Field(ge=0, le=1)


class MissedOption(BaseModel):
    key: str
    text: str
    missed_rate: float = Field(ge=0, le=1)


class InsightStage(BaseModel):
    stage: DecisionStage
    label: str
    options: list[InsightOption] = Field(default_factory=list)
    missed_correct: list[MissedOption] = Field(default_factory=list)


class WrongDiagnosis(BaseModel):
    text: str
    count: int


class KeyTestEffect(BaseModel):
    """Diagnostic accuracy of those who ordered a correct work-up option vs those who did not."""

    key: str
    text: str
    chose_rate: float = Field(ge=0, le=1)
    dx_accuracy_if_chosen: float | None = Field(default=None, ge=0, le=1)
    dx_accuracy_if_not: float | None = Field(default=None, ge=0, le=1)


class CaseInsights(BaseModel):
    slug: str
    title: str
    cohort_size: int
    cohort_is_simulated: bool
    diagnosis_accuracy: float | None = Field(default=None, ge=0, le=1)
    top_wrong_diagnoses: list[WrongDiagnosis] = Field(default_factory=list)
    stages: list[InsightStage] = Field(default_factory=list)
    key_tests: list[KeyTestEffect] = Field(default_factory=list)
    benchmarks: list[Benchmark] = Field(default_factory=list)
