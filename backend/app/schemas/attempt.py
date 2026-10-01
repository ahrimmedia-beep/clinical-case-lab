"""Attempt (answers) in, debrief out."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from app.schemas.case import Diagnosis, StageItem
from app.schemas.common import StrictModel
from app.stages import Stage

OptionKey = Annotated[str, StringConstraints(pattern=r"^[A-L]$")]


class MultiSelectStage(StrEnum):
    INTERVIEW = "interview"
    DIFFERENTIAL = "differential"
    WORKUP = "workup"
    TREATMENT = "treatment"


class AttemptIn(StrictModel):
    choices: dict[MultiSelectStage, list[OptionKey]] = Field(default_factory=dict)
    diagnosis_text: str = Field(default="", max_length=200)
    confidence: int = Field(ge=1, le=5)
    duration_ms: int | None = Field(default=None, ge=0, le=3_600_000)


class RevealIn(StrictModel):
    stage: Literal["interview", "workup"]
    option_keys: list[OptionKey] = Field(max_length=12)


class RevealOut(BaseModel):
    key: str
    reveal: str


class OptionState(StrEnum):
    RIGHT = "right"
    WRONG = "wrong"
    MISSED = "missed"
    NEUTRAL = "neutral"


class Calibration(StrEnum):
    OVERCONFIDENT = "overconfident"
    UNDERCONFIDENT = "underconfident"
    CALIBRATED = "calibrated"


class DebriefOption(BaseModel):
    key: str
    text: str
    chosen: bool
    state: OptionState
    is_harmful: bool
    feedback: str | None = None
    reveal: str | None = None
    pick_rate: float | None = Field(default=None, ge=0, le=1)


class DebriefStage(BaseModel):
    number: int
    key: Stage
    label: str
    hint: str
    kind: Literal["given", "decision"]
    scored: bool
    right: int = 0
    wrong: int = 0
    missed: int = 0
    points: int = 0
    max_points: int = 0
    explanation: str | None = None
    options: list[DebriefOption] = Field(default_factory=list)
    items: list[StageItem] = Field(default_factory=list)


class DiagnosisResult(BaseModel):
    your_text: str
    correct: bool
    answered: bool
    confidence: int
    calibration: Calibration


class HistogramBin(BaseModel):
    points: int
    count: int


class AttemptResult(BaseModel):
    attempt_id: int
    case_slug: str
    points: int
    max_points: int
    right: int
    wrong: int
    missed: int
    harmful: int
    total_decisions: int
    percentile: float | None = Field(default=None, ge=0, le=100)
    cohort_size: int
    cohort_is_simulated: bool
    histogram: list[HistogramBin]
    final_diagnosis: Diagnosis
    diagnosis: DiagnosisResult
    stages: list[DebriefStage]
