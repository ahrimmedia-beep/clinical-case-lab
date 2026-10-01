"""Step 1: de-identified text -> ExtractedFacts, with a validate-and-repair loop."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import ValidationError

from app.schemas.extract import Usage
from pipeline.models import ExtractedFacts, LLMExtractedFacts, to_extracted_facts
from pipeline.prompts import load_prompt, with_repair
from pipeline.providers.base import (
    InvalidOutput,
    LLMProvider,
    ProviderError,
    add_usage,
    format_validation_errors,
    usage_of,
)

MAX_REPAIRS = 2  # up to 3 calls in total


@dataclass(frozen=True)
class ExtractionOutcome:
    facts: ExtractedFacts
    attempts: int
    usage: Usage
    warnings: list[str]


class ExtractionFailed(ProviderError):
    """The model never produced valid facts (HTTP 502). `last_errors` is for logs/evals only."""

    def __init__(self, attempts: int, last_errors: str, usage: Usage) -> None:
        super().__init__(f"the model output failed validation {attempts} times")
        self.attempts = attempts
        self.last_errors = last_errors
        self.usage = usage


def render_extract_user(text: str) -> str:
    return f"<clinical_text>\n{text}\n</clinical_text>"


async def extract_facts(text: str, provider: LLMProvider) -> ExtractionOutcome:
    system = load_prompt("extract")
    base_user = render_extract_user(text)
    usage = Usage()
    errors: str | None = None
    for attempt in range(1, MAX_REPAIRS + 2):
        user = base_user if errors is None else with_repair(base_user, errors)
        try:
            result = await provider.generate(system=system, user=user, schema=LLMExtractedFacts)
        except InvalidOutput as exc:
            usage = add_usage(usage, exc.usage)
            errors = exc.errors
            continue
        usage = add_usage(usage, usage_of(result))
        try:
            facts, warnings = to_extracted_facts(result.parsed)
        except ValidationError as exc:
            errors = format_validation_errors(exc)
            continue
        return ExtractionOutcome(facts=facts, attempts=attempt, usage=usage, warnings=warnings)
    raise ExtractionFailed(MAX_REPAIRS + 1, errors or "", usage)
