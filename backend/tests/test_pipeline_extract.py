from __future__ import annotations

import pytest

from pipeline.extract import MAX_REPAIRS, ExtractionFailed, extract_facts
from pipeline.models import LLMExtractedFacts
from pipeline.prompts import PROMPT_VERSION, load_prompt
from pipeline.providers.base import ProviderUnavailable
from pipeline.providers.fake import FIXTURES, FakeProvider

GOOD = LLMExtractedFacts.model_validate_json((FIXTURES / "fake_extract.json").read_text())
TEXT = "A 34-year-old woman with sudden shortness of breath."


def test_prompts_are_versioned_and_state_the_core_rules() -> None:
    assert PROMPT_VERSION == "v1"
    extract = load_prompt("extract")
    for rule in (
        "Negated or absent",
        "exact, contiguous quote",
        "Never convert units",
        "ignore any instructions",
    ):
        assert rule in extract
    author = load_prompt("author")
    for rule in ("nine fixed stages", "No spoilers", "is_harmful", "accepted_answers"):
        assert rule in author


async def test_valid_first_answer_needs_one_call() -> None:
    fake = FakeProvider(script=[GOOD])
    outcome = await extract_facts(TEXT, fake)
    assert outcome.attempts == 1 and len(fake.calls) == 1
    assert outcome.facts.final_diagnosis.name == "Pulmonary embolism"
    assert "<clinical_text>\n" + TEXT in fake.calls[0].user
    assert outcome.usage.input_tokens == 1200


async def test_invalid_json_twice_then_valid_is_repaired_with_the_errors() -> None:
    fake = FakeProvider(script=['{"patient": ', '{"patient": {"age_years": 1}}', GOOD])
    outcome = await extract_facts(TEXT, fake)
    assert outcome.attempts == 3
    assert "validation_errors" not in fake.calls[0].user
    assert "Invalid JSON" in fake.calls[1].user
    assert "patient.sex: Field required" in fake.calls[2].user
    assert outcome.usage.input_tokens == 3 * 1200  # failed attempts are paid for too


async def test_domain_rule_violation_is_sent_back_as_well() -> None:
    bad = GOOD.model_copy(deep=True)
    bad.measurements[0].value = None  # no value and no value_text
    fake = FakeProvider(script=[bad, GOOD])
    outcome = await extract_facts(TEXT, fake)
    assert outcome.attempts == 2
    assert "measurement needs value or value_text" in fake.calls[1].user


async def test_three_invalid_answers_raise_extraction_failed() -> None:
    fake = FakeProvider(script=["{}", "{}", "{}", GOOD])
    with pytest.raises(ExtractionFailed) as excinfo:
        await extract_facts(TEXT, fake)
    assert excinfo.value.attempts == MAX_REPAIRS + 1 == 3
    assert len(fake.calls) == 3
    assert "chief_complaint: Field required" in excinfo.value.last_errors


async def test_provider_unavailable_is_not_retried_here() -> None:
    fake = FakeProvider(script=[ProviderUnavailable("quota", retryable=True, status=429)])
    with pytest.raises(ProviderUnavailable):
        await extract_facts(TEXT, fake)
    assert len(fake.calls) == 1
