"""Raw clinical text in, LLM-built case with evidence spans out."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from app.schemas.case import ClinicalCase
from app.schemas.common import StrictModel


class Provider(StrEnum):
    GEMINI = "gemini"
    CLAUDE = "claude"


class ExtractRequest(StrictModel):
    text: str = Field(min_length=50, max_length=20_000)
    provider: Provider = Provider.GEMINI
    model: str | None = Field(default=None, max_length=80)


class EvidenceSpan(BaseModel):
    path: str  # e.g. "findings[3]", "measurements[0]", "final_diagnosis"
    quote: str
    start: int | None = None
    end: int | None = None
    grounded: bool


class PhiCount(BaseModel):
    label: str
    count: int


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0


class ExtractResponse(BaseModel):
    case: ClinicalCase
    source_text: str
    spans: list[EvidenceSpan]
    phi: list[PhiCount]
    grounded_ratio: float = Field(ge=0, le=1)
    warnings: list[str]
    provider: Provider
    model: str
    prompt_version: str
    usage: Usage
