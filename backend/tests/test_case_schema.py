from __future__ import annotations

import copy
from typing import Any

import pytest
from pydantic import ValidationError

from app.schemas.attempt import AttemptIn, AttemptResult
from app.schemas.case import CasePublic, CaseSummary, ClinicalCase
from app.schemas.extract import ExtractRequest


def make(case: dict[str, Any], **changes: Any) -> dict[str, Any]:
    data = copy.deepcopy(case)
    data.update(changes)
    return data


def decision(data: dict[str, Any], stage: str) -> dict[str, Any]:
    found: dict[str, Any] = next(d for d in data["decisions"] if d["stage"] == stage)
    return found


def test_fixture_is_valid(case_pe: dict[str, Any]) -> None:
    case = ClinicalCase.model_validate(case_pe)
    assert case.final_diagnosis.name == "Pulmonary embolism"
    assert case.diagnosis_terms() == ["Pulmonary embolism", "PE", "Pulmonary thromboembolism"]


def test_unknown_field_is_rejected(case_pe: dict[str, Any]) -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ClinicalCase.model_validate(make(case_pe, hacker=True))


def test_duplicate_stage_is_rejected(case_pe: dict[str, Any]) -> None:
    data = make(case_pe)
    # Replace the interview decision with a second workup one: still <= 5 decisions,
    # so the duplicate-stage validator (not the length cap) must reject it.
    data["decisions"] = [d for d in data["decisions"] if d["stage"] != "interview"]
    data["decisions"].append(copy.deepcopy(decision(data, "workup")))
    with pytest.raises(ValidationError, match="one decision per stage"):
        ClinicalCase.model_validate(data)


def test_diagnosis_decision_is_required(case_pe: dict[str, Any]) -> None:
    data = make(case_pe)
    data["decisions"] = [d for d in data["decisions"] if d["stage"] != "diagnosis"]
    with pytest.raises(ValidationError, match="diagnosis decision is required"):
        ClinicalCase.model_validate(data)


def test_diagnosis_decision_cannot_have_options(case_pe: dict[str, Any]) -> None:
    data = make(case_pe)
    decision(data, "diagnosis")["options"] = copy.deepcopy(decision(data, "workup")["options"])
    with pytest.raises(ValidationError, match="free-text"):
        ClinicalCase.model_validate(data)


def test_multi_select_needs_a_correct_option(case_pe: dict[str, Any]) -> None:
    data = make(case_pe)
    for option in decision(data, "treatment")["options"]:
        option["is_correct"] = False
    with pytest.raises(ValidationError, match="at least one correct option"):
        ClinicalCase.model_validate(data)


def test_duplicate_option_keys_are_rejected(case_pe: dict[str, Any]) -> None:
    data = make(case_pe)
    decision(data, "workup")["options"][1]["key"] = "A"
    with pytest.raises(ValidationError, match="option keys must be unique"):
        ClinicalCase.model_validate(data)


def test_harmful_option_cannot_be_correct(case_pe: dict[str, Any]) -> None:
    data = make(case_pe)
    decision(data, "treatment")["options"][2]["is_correct"] = True
    with pytest.raises(ValidationError, match="harmful option cannot be correct"):
        ClinicalCase.model_validate(data)


def test_reveal_only_on_interview_and_workup(case_pe: dict[str, Any]) -> None:
    data = make(case_pe)
    decision(data, "treatment")["options"][0]["reveal"] = "something"
    with pytest.raises(ValidationError, match="reveal is only allowed"):
        ClinicalCase.model_validate(data)


@pytest.mark.parametrize("field", ["title", "vignette", "chief_complaint"])
def test_diagnosis_must_not_leak(case_pe: dict[str, Any], field: str) -> None:
    data = make(case_pe, **{field: "Classic pulmonary embolism after a flight in a young woman"})
    with pytest.raises(ValidationError, match="leaks the diagnosis"):
        ClinicalCase.model_validate(data)


def test_short_abbreviation_leak_is_word_bounded(case_pe: dict[str, Any]) -> None:
    ok = make(case_pe, vignette=case_pe["vignette"] + " She appears pale.")
    ClinicalCase.model_validate(ok)  # "pale" must not trip the "PE" alias
    bad = make(case_pe)
    decision(bad, "workup")["prompt"] = "Which tests confirm PE?"
    with pytest.raises(ValidationError, match="leaks the diagnosis"):
        ClinicalCase.model_validate(bad)


def test_public_view_has_no_answer_fields() -> None:
    forbidden = {
        "is_correct",
        "is_harmful",
        "feedback",
        "explanation",
        "accepted_answers",
        "reveal",
        "final_diagnosis",
        "differential",
    }
    schema = CasePublic.model_json_schema()
    # Stage *values* such as "differential" are allowed; answer *fields* are not.
    names = set(schema.get("properties", {}))
    for sub in schema.get("$defs", {}).values():
        names |= set(sub.get("properties", {}))
    assert not forbidden & names, forbidden & names


def test_attempt_in_validates_keys_and_confidence() -> None:
    ok = AttemptIn.model_validate(
        {"choices": {"workup": ["A", "B"]}, "diagnosis_text": "PE", "confidence": 4}
    )
    assert ok.choices
    with pytest.raises(ValidationError):
        AttemptIn.model_validate({"choices": {"diagnosis": ["A"]}, "confidence": 3})
    with pytest.raises(ValidationError):
        AttemptIn.model_validate({"choices": {"workup": ["Z9"]}, "confidence": 3})
    with pytest.raises(ValidationError):
        AttemptIn.model_validate({"choices": {}, "confidence": 6})


def test_attempt_result_schema_exposes_debrief_fields() -> None:
    props = AttemptResult.model_json_schema()["properties"]
    for field in (
        "points",
        "max_points",
        "right",
        "wrong",
        "missed",
        "percentile",
        "histogram",
        "stages",
        "diagnosis",
        "final_diagnosis",
    ):
        assert field in props


def test_extract_request_limits_text() -> None:
    with pytest.raises(ValidationError):
        ExtractRequest.model_validate({"text": "too short", "provider": "gemini"})
    with pytest.raises(ValidationError):
        ExtractRequest.model_validate({"text": "x" * 20_001, "provider": "gemini"})
    ExtractRequest.model_validate({"text": "x" * 60, "provider": "claude"})


def test_reveal_that_names_the_diagnosis_is_a_leak(case_pe: dict[str, Any]) -> None:
    data = make(case_pe)
    workup = decision(data, "workup")
    workup["options"][0]["reveal"] = "CT angiography: findings consistent with pulmonary embolism."
    with pytest.raises(ValidationError, match="reveal leaks the diagnosis"):
        ClinicalCase.model_validate(data)


def test_source_text_is_accepted_and_public_views_carry_review_status(
    case_pe: dict[str, Any],
) -> None:
    data = make(case_pe)
    data["source"] = {"kind": "llm", "provider": "gemini", "model": "m", "text": "raw text"}
    assert ClinicalCase.model_validate(data).source is not None
    assert "review_status" in CasePublic.model_json_schema()["properties"]
    assert "review_status" in CaseSummary.model_json_schema()["properties"]
    assert "benchmarks" in AttemptResult.model_json_schema()["properties"]
