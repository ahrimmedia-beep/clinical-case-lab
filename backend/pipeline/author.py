"""Step 2: facts -> title, vignette and decisions; one re-ask if the case fails validation
(most often the deterministic no-leak rule: the diagnosis named in a title or prompt)."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import ValidationError

from app.schemas.case import CaseSource, ClinicalCase
from app.schemas.extract import Usage
from pipeline.assemble import assemble_case
from pipeline.models import ExtractedFacts, LLMAuthoredCase
from pipeline.prompts import load_prompt, with_repair
from pipeline.providers.base import (
    InvalidOutput,
    LLMProvider,
    ProviderError,
    add_usage,
    format_validation_errors,
    usage_of,
)

MAX_ATTEMPTS = 2  # first try + one re-ask


@dataclass(frozen=True)
class AuthoringOutcome:
    case: ClinicalCase
    attempts: int
    usage: Usage


class AuthoringFailed(ProviderError):
    def __init__(self, attempts: int, last_errors: str, usage: Usage) -> None:
        super().__init__(f"the authored case failed validation {attempts} times")
        self.attempts = attempts
        self.last_errors = last_errors
        self.usage = usage


def render_author_user(facts: ExtractedFacts) -> str:
    return f"<facts>\n{facts.model_dump_json(indent=2)}\n</facts>"


async def author_case(
    facts: ExtractedFacts, provider: LLMProvider, source: CaseSource
) -> AuthoringOutcome:
    system = load_prompt("author")
    base_user = render_author_user(facts)
    usage = Usage()
    errors: str | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        user = base_user if errors is None else with_repair(base_user, errors)
        try:
            result = await provider.generate(system=system, user=user, schema=LLMAuthoredCase)
        except InvalidOutput as exc:
            usage = add_usage(usage, exc.usage)
            errors = exc.errors
            continue
        usage = add_usage(usage, usage_of(result))
        try:
            case = assemble_case(facts, result.parsed, source)
        except ValidationError as exc:
            errors = format_validation_errors(exc)
            continue
        return AuthoringOutcome(case=case, attempts=attempt, usage=usage)
    raise AuthoringFailed(MAX_ATTEMPTS, errors or "", usage)
