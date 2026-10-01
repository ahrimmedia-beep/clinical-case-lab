"""★2 physician review: answer key + a server-side checklist (no LLM)."""

from __future__ import annotations

from typing import Any

import pytest

from app.repository.review import build_case_review
from app.schemas.case import ClinicalCase, ReviewStatus
from app.schemas.review import CaseReview, ReviewChecklistItem

SOURCE = (
    "A 34-year-old woman returned yesterday from a 14-hour flight. She has sharp right-sided "
    "chest pain that worsens on inspiration and takes a combined oral contraceptive. Heart rate "
    "112, SpO2 91% on room air. D-dimer 2.4 mg/L FEU. CT pulmonary angiography shows a filling "
    "defect in the right lower lobe pulmonary artery, consistent with acute pulmonary embolism. "
    "Pneumothorax was considered and excluded."
)


def llm_case(case_pe: dict[str, Any], source_text: str = SOURCE) -> ClinicalCase:
    data = {
        **case_pe,
        "final_diagnosis": {**case_pe["final_diagnosis"], "evidence": "acute pulmonary embolism"},
        "differential": [{**case_pe["differential"][0], "evidence": "Pneumothorax was considered"}],
        "source": {
            "kind": "llm",
            "provider": "gemini",
            "model": "gemini-3.8-flash",
            "prompt_version": "v3",
            "text": source_text,
        },
    }
    return ClinicalCase.model_validate(data)


def check(review: CaseReview, check_id: str) -> ReviewChecklistItem:
    return next(c for c in review.checklist if c.id == check_id)


@pytest.fixture
def review(case_pe: dict[str, Any]) -> CaseReview:
    return build_case_review("s-abc123", llm_case(case_pe), ReviewStatus.DRAFT)


def test_review_carries_the_full_answer_key(review: CaseReview) -> None:
    assert (review.slug, review.review_status) == ("s-abc123", "draft")
    assert review.source.model_dump() == {
        "kind": "llm",
        "provider": "gemini",
        "model": "gemini-3.8-flash",
        "prompt_version": "v3",
    }
    key = review.answer_key
    assert key.final_diagnosis.name == "Pulmonary embolism"
    assert key.accepted_answers == ["Pulmonary embolism", "PE", "Pulmonary thromboembolism"]
    assert [s.stage for s in key.stages] == [
        "interview",
        "differential",
        "workup",
        "diagnosis",
        "treatment",
    ]
    treatment = key.stages[-1]
    assert treatment.explanation and treatment.options[2].is_harmful is True
    assert treatment.options[2].feedback is not None
    workup = key.stages[2]
    assert workup.options[0].reveal == "Filling defect in the right lower lobe pulmonary artery."


def test_checklist_order_and_ids(review: CaseReview) -> None:
    assert [c.id for c in review.checklist] == [
        "grounding",
        "harmful_options",
        "no_leak",
        "answer_key",
        "phi",
    ]


def test_grounding_flags_evidence_missing_from_the_source(review: CaseReview) -> None:
    grounding = check(review, "grounding")
    assert grounding.status == "warn"
    # "left calf is swollen and tender" is not in SOURCE; everything else is.
    assert len(grounding.items) == 1
    assert grounding.items[0].startswith('findings[3] "Swollen, tender left calf"')
    assert "1 of 10" in grounding.detail


def test_fully_grounded_case_is_ok(case_pe: dict[str, Any]) -> None:
    source = SOURCE + " Her left calf is swollen and tender."
    review = build_case_review("s-abc123", llm_case(case_pe, source), ReviewStatus.DRAFT)
    assert check(review, "grounding").status == "ok"
    assert check(review, "grounding").items == []


def test_harmful_options_are_listed_for_sign_off(review: CaseReview) -> None:
    harmful = check(review, "harmful_options")
    assert harmful.status == "warn"
    assert harmful.items == ["treatment C: Systemic thrombolysis"]


def test_no_leak_passes_for_a_valid_case(review: CaseReview) -> None:
    no_leak = check(review, "no_leak")
    assert no_leak.status == "ok" and no_leak.items == []
    assert "withheld" in no_leak.detail  # given-stage items that name the diagnosis are hidden


def test_no_leak_fails_on_a_leaking_reveal(case_pe: dict[str, Any]) -> None:
    case = llm_case(case_pe)
    workup = next(d for d in case.decisions if d.stage == "workup")
    workup.options[1].reveal = "Raised, typical of a PE."  # bypasses the ingest validator
    review = build_case_review("s-abc123", case, ReviewStatus.DRAFT)
    no_leak = check(review, "no_leak")
    assert no_leak.status == "fail"
    assert no_leak.items == ["decisions[workup].options[B].reveal names 'PE'"]


def test_answer_key_lists_the_pathway(review: CaseReview) -> None:
    answer_key = check(review, "answer_key")
    assert answer_key.status == "ok"
    assert answer_key.items == [
        "interview: A Any recent long travel or immobility?; B Does she take any hormonal "
        "medication?",
        "differential: A Pulmonary embolism; B Pneumothorax",
        "workup: A CT pulmonary angiography; B D-dimer",
        "diagnosis: Pulmonary embolism (also accepted: PE, Pulmonary thromboembolism)",
        "treatment: A Start anticoagulation (apixaban or LMWH); B Stop the combined oral "
        "contraceptive",
    ]


def test_phi_check_passes_on_clean_text_and_fails_on_identifiers(
    case_pe: dict[str, Any], review: CaseReview
) -> None:
    assert check(review, "phi").status == "ok"
    leaky = llm_case(case_pe, SOURCE + " Contact: jane.doe@example.com, 555-123-4567.")
    phi = check(build_case_review("s-abc123", leaky, ReviewStatus.DRAFT), "phi")
    assert phi.status == "fail"
    assert phi.items == ["EMAIL", "PHONE"]


def test_manual_case_without_source_text(case_pe: dict[str, Any]) -> None:
    review = build_case_review(
        "s-abc123", ClinicalCase.model_validate(case_pe), ReviewStatus.APPROVED
    )
    assert review.review_status == "approved" and review.source.kind == "manual"
    grounding = check(review, "grounding")
    assert grounding.status == "warn" and "no source text" in grounding.detail.lower()
    assert check(review, "phi").status == "ok"
