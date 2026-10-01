from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from pipeline.models import (
    ExtractedFacts,
    LLMAuthoredCase,
    LLMExtractedFacts,
    from_extracted_facts,
    to_extracted_facts,
)
from pipeline.pricing import allowed_models, cost_usd, default_model, load_pricing


def llm_facts(**changes: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "patient": {"age_years": 34, "sex": "female"},
        "chief_complaint": "Sudden shortness of breath",
        "findings": [
            {
                "category": "symptom",
                "text": "Pleuritic chest pain",
                "evidence": "sharp right-sided chest pain",
            },
        ],
        "measurements": [
            {
                "kind": "vital",
                "name": "SpO2",
                "value": 91,
                "value_text": "",
                "unit": "%",
                "flag": "low",
                "evidence": "SpO2 91% on room air",
            },
            {
                "kind": "vital",
                "name": "Blood pressure",
                "value": None,
                "value_text": "128/76",
                "unit": "mmHg",
                "flag": "not_stated",
                "evidence": "BP 128/76 mmHg",
            },
        ],
        "final_diagnosis": {
            "name": "Pulmonary embolism",
            "icd10": "i26.99",
            "evidence": "acute pulmonary embolism",
        },
        "differential": [{"name": "Pneumothorax", "icd10": "not sure", "evidence": ""}],
    }
    data.update(changes)
    return data


def _count_unions_and_optionals(model: type[BaseModel]) -> tuple[int, int]:
    schema = model.model_json_schema()
    objects: list[dict[str, Any]] = [schema, *schema.get("$defs", {}).values()]
    unions = optionals = 0
    for obj in objects:
        required = set(obj.get("required", []))
        for name, prop in obj.get("properties", {}).items():
            if "anyOf" in prop or isinstance(prop.get("type"), list):
                unions += 1
            if name not in required:
                optionals += 1
    return unions, optionals


@pytest.mark.parametrize("model", [LLMExtractedFacts, LLMAuthoredCase])
def test_llm_schemas_are_claude_safe(model: type[BaseModel]) -> None:
    unions, optionals = _count_unions_and_optionals(model)
    assert unions <= 16
    assert optionals == 0  # limit is 24; we use none at all
    text = str(model.model_json_schema())
    for constraint in ("maxLength", "minLength", "maximum", "minimum", "maxItems"):
        assert constraint not in text, constraint
    assert "'additionalProperties': False" in text


def test_converter_maps_sentinels_to_none_and_cleans_icd10() -> None:
    facts, warnings = to_extracted_facts(LLMExtractedFacts.model_validate(llm_facts()))
    assert facts.final_diagnosis.icd10 == "I26.99"
    assert facts.differential[0].icd10 is None and facts.differential[0].evidence is None
    bp = facts.measurements[1]
    assert bp.value is None and bp.value_text == "128/76" and bp.flag is None
    assert facts.patient.display_name is None
    assert warnings == ["differential[0].icd10 'NOT SURE' dropped: not an ICD-10 code"]


def test_converter_raises_on_domain_rule_violation() -> None:
    bad = llm_facts(
        measurements=[
            {
                "kind": "lab",
                "name": "D-dimer",
                "value": None,
                "value_text": "",
                "unit": "",
                "flag": "not_stated",
                "evidence": "D-dimer",
            },
        ]
    )
    with pytest.raises(ValidationError, match="measurement needs value or value_text"):
        to_extracted_facts(LLMExtractedFacts.model_validate(bad))


def test_round_trip_domain_to_llm_and_back() -> None:
    facts, _ = to_extracted_facts(LLMExtractedFacts.model_validate(llm_facts()))
    again, _ = to_extracted_facts(from_extracted_facts(facts))
    assert again == facts
    assert isinstance(again, ExtractedFacts)


def test_pricing_table_is_the_four_models_of_the_spec() -> None:
    assert sorted(load_pricing()) == [
        "claude/claude-opus-4-8",
        "claude/claude-opus-5-5",
        "claude/claude-sonnet-5",
        "gemini/gemini-3.8-flash",
    ]
    assert allowed_models("gemini") == ["gemini-3.8-flash"]
    assert allowed_models("claude") == ["claude-sonnet-5", "claude-opus-4-8", "claude-opus-5-5"]
    assert default_model("gemini") == "gemini-3.8-flash"
    assert default_model("claude") == "claude-sonnet-5"
    for retired in ("claude-sonnet-5-5", "claude-haiku-4-5@20251001", "gemini-3.5-flash-lite"):
        assert retired not in allowed_models("claude") + allowed_models("gemini")


def test_pricing_cost_per_call() -> None:
    # 10k in + 2k out: Sonnet 5 = 0.02 + 0.02, Opus 4.8 = 0.05 + 0.05, Opus 5.5 = 0.04 + 0.04
    assert cost_usd("claude", "claude-sonnet-5", 10_000, 2_000) == pytest.approx(0.04)
    assert cost_usd("claude", "claude-opus-4-8", 10_000, 2_000) == pytest.approx(0.10)
    assert cost_usd("claude", "claude-opus-5-5", 10_000, 2_000) == pytest.approx(0.08)
    assert cost_usd("gemini", "gemini-3.8-flash", 1_000_000, 0) == pytest.approx(0.75)
    assert cost_usd("gemini", "gemini-3.8-flash", 0, 1_000_000) == pytest.approx(3.75)
    assert cost_usd("fake", "fake-gold", 5_000, 5_000) == 0.0
