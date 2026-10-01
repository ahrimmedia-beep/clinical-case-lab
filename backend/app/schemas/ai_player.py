"""AI models play a stored case blinded, through the same scoring path as physicians."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.attempt import Calibration
from app.schemas.common import StrictModel
from app.schemas.extract import Provider


class AiAttemptRequest(StrictModel):
    provider: Provider
    model: str | None = Field(default=None, max_length=80)


class AiAttemptSummary(BaseModel):
    attempt_id: int
    label: str  # "ai:<model>"
    provider: str
    model: str
    points: int
    max_points: int
    diagnosis_text: str
    diagnosis_correct: bool
    confidence: int
    calibration: Calibration
    latency_ms: int
    cost_usd: float
