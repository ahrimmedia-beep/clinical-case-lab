"""Physician review of AI-drafted cases ("AI-assisted, not AI-generated")."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from app.schemas.case import Diagnosis, ReviewStatus, SourceKind
from app.stages import DecisionStage


class CheckStatus(StrEnum):
    OK = "ok"
    WARN = "warn"
    FAIL = "fail"


class ReviewChecklistItem(BaseModel):
    id: str  # grounding | harmful_options | no_leak | answer_key | phi
    label: str
    status: CheckStatus
    detail: str
    items: list[str] = Field(default_factory=list)


class AnswerKeyOption(BaseModel):
    key: str
    text: str
    is_correct: bool
    is_harmful: bool
    feedback: str | None = None
    reveal: str | None = None


class AnswerKeyStage(BaseModel):
    stage: DecisionStage
    prompt: str
    explanation: str
    options: list[AnswerKeyOption] = Field(default_factory=list)


class AnswerKey(BaseModel):
    final_diagnosis: Diagnosis
    accepted_answers: list[str]
    stages: list[AnswerKeyStage]


class ReviewSource(BaseModel):
    kind: SourceKind
    provider: str | None = None
    model: str | None = None
    prompt_version: str | None = None


class CaseReview(BaseModel):
    slug: str
    title: str
    review_status: ReviewStatus
    source: ReviewSource
    answer_key: AnswerKey
    checklist: list[ReviewChecklistItem]


class ApproveResponse(BaseModel):
    slug: str
    review_status: ReviewStatus
    reviewed_at: datetime
