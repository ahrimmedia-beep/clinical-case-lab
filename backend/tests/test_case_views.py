from __future__ import annotations

import copy
from typing import Any

import pytest

from app.case_views import (
    WITHHELD_TEXT,
    CohortStats,
    build_attempt_result,
    build_case_public,
    build_debrief_stages,
    build_reveals,
    default_review_status,
    format_value,
    present_stages,
)
from app.schemas.attempt import AttemptIn, Benchmark, Calibration, HistogramBin, OptionState
from app.schemas.case import ClinicalCase, ReviewStatus
from app.scoring import score_attempt
from app.stages import Stage

ALL_STAGES = [
    "presenting_complaint",
    "history",
    "interview",
    "examination",
    "differential",
    "workup",
    "results",
    "diagnosis",
    "treatment",
]


@pytest.fixture
def case(case_pe: dict[str, Any]) -> ClinicalCase:
    return ClinicalCase.model_validate(case_pe)


def by_key(stages: list[Any], key: str) -> Any:
    return next(s for s in stages if s.key == key)


def test_format_value() -> None:
    assert format_value(112.0) == "112"
    assert format_value(2.4) == "2.4"
    assert format_value(0.00012) == "0.00012"
    assert format_value(1450.0) == "1450"
    assert format_value(-0.0) == "0"
    assert format_value(None) is None


def test_public_view_has_all_nine_stages_in_order(case: ClinicalCase) -> None:
    public = build_case_public(7, "sudden-breathlessness-abc123", case)
    assert public.id == 7 and public.slug == "sudden-breathlessness-abc123"
    assert [s.key for s in public.stages] == ALL_STAGES
    assert [s.number for s in public.stages] == list(range(1, 10))
    assert public.source_kind == "manual"
    assert public.review_status == "approved"


def test_given_stages_carry_their_items(case: ClinicalCase) -> None:
    stages = build_case_public(1, "s-abc123", case).stages
    history = [i.text for i in by_key(stages, "history").items]
    assert history == [
        "Pleuritic right-sided chest pain",
        "14-hour flight the day before",
        "Combined oral contraceptive pill",
    ]
    exam = by_key(stages, "examination").items
    assert [i.text for i in exam] == ["Swollen, tender left calf", "Heart rate", "SpO2"]
    hr = exam[1]
    assert (hr.kind, hr.category, hr.value, hr.unit, hr.flag) == (
        "measurement",
        "vital",
        "112",
        "bpm",
        "high",
    )
    results = by_key(stages, "results").items
    assert [i.text for i in results][-1] == "D-dimer"
    assert results[-1].value == "2.4"
    assert by_key(stages, "presenting_complaint").items == []


def test_decision_stages_expose_prompt_and_option_text_only(case: ClinicalCase) -> None:
    stages = build_case_public(1, "s-abc123", case).stages
    workup = by_key(stages, "workup")
    assert workup.input == "multi_select"
    assert [(o.key, o.text) for o in workup.options] == [
        ("A", "CT pulmonary angiography"),
        ("B", "D-dimer"),
        ("C", "Spirometry"),
    ]
    diagnosis = by_key(stages, "diagnosis")
    assert diagnosis.input == "free_text" and diagnosis.options == []
    assert diagnosis.prompt == "What is your diagnosis?"


def test_public_json_contains_no_answer_material(case: ClinicalCase) -> None:
    dumped = build_case_public(1, "s-abc123", case).model_dump_json()
    for secret in (
        '"is_correct"',
        '"is_harmful"',
        '"feedback"',
        '"explanation"',
        '"reveal"',
        '"accepted_answers"',
        "Thrombolysis is reserved",
        "Haemodynamically stable",
        "Yes, a 14-hour flight yesterday.",
        "Low yield for an acute presentation",
    ):
        assert secret not in dumped, secret


def test_spoiler_items_are_withheld_in_public_view(case_pe: dict[str, Any]) -> None:
    data = copy.deepcopy(case_pe)
    data["findings"].append(
        {"category": "imaging", "text": "CT impression: acute pulmonary embolism", "evidence": None}
    )
    data["findings"].append(
        {"category": "exam", "text": "She looks pale and anxious", "evidence": None}
    )
    data["measurements"].append(
        {
            "kind": "lab",
            "name": "V/Q scan",
            "value": None,
            "value_text": "High probability for PE",
            "unit": None,
            "flag": "abnormal",
            "evidence": None,
        }
    )
    case = ClinicalCase.model_validate(data)
    stages = build_case_public(1, "s-abc123", case).stages
    results = by_key(stages, "results").items
    withheld = [i for i in results if i.withheld]
    assert len(withheld) == 2
    assert all(i.text == WITHHELD_TEXT and i.value is None and i.flag is None for i in withheld)
    exam_texts = [i.text for i in by_key(stages, "examination").items]
    assert "She looks pale and anxious" in exam_texts  # "pale" must not trip "PE"

    score = score_attempt(case, AttemptIn.model_validate({"confidence": 3}))
    debrief = build_debrief_stages(case, score, {})
    debrief_results = by_key(debrief, "results").items
    assert not any(i.withheld for i in debrief_results)
    assert "CT impression: acute pulmonary embolism" in [i.text for i in debrief_results]
    assert "High probability for PE" in [i.value for i in debrief_results]


def test_absent_stages_are_skipped(case_pe: dict[str, Any]) -> None:
    data = copy.deepcopy(case_pe)
    data["decisions"] = [d for d in data["decisions"] if d["stage"] != "interview"]
    data["findings"] = [f for f in data["findings"] if f["category"] != "imaging"]
    data["measurements"] = [m for m in data["measurements"] if m["kind"] != "lab"]
    keys = [s.key for s in present_stages(ClinicalCase.model_validate(data))]
    assert Stage.INTERVIEW not in keys and Stage.RESULTS not in keys
    assert keys[0] is Stage.PRESENTING_COMPLAINT


def test_build_reveals_returns_only_chosen_options_with_a_reveal(case: ClinicalCase) -> None:
    reveals = build_reveals(case, Stage.WORKUP, ["C", "A"])
    assert [(r.key, r.reveal) for r in reveals] == [
        ("A", "Filling defect in the right lower lobe pulmonary artery."),
        ("C", "Not performed."),
    ]


def test_debrief_marks_options_and_pick_rates(case: ClinicalCase) -> None:
    attempt = AttemptIn.model_validate(
        {
            "choices": {"workup": ["A", "C"], "treatment": ["A", "C"]},
            "diagnosis_text": "pulmonary emboli",
            "confidence": 5,
        }
    )
    score = score_attempt(case, attempt)
    stages = build_debrief_stages(case, score, {("workup", "A"): 0.5, ("workup", "B"): 0.25})
    assert [s.key for s in stages] == ALL_STAGES
    workup = by_key(stages, "workup")
    assert (workup.right, workup.wrong, workup.missed) == (1, 1, 1)
    options = {o.key: o for o in workup.options}
    assert options["A"].state is OptionState.RIGHT and options["A"].pick_rate == 0.5
    assert options["C"].state is OptionState.WRONG and options["C"].pick_rate is None
    assert options["C"].feedback == "Not useful in the acute setting."
    assert options["A"].reveal == "Filling defect in the right lower lobe pulmonary artery."
    assert workup.explanation is not None
    treatment = by_key(stages, "treatment")
    assert (treatment.points, treatment.max_points) == (0, 2)  # the harmful pick zeroes it
    assert {o.key: o.is_harmful for o in treatment.options}["C"] is True
    diagnosis = by_key(stages, "diagnosis")
    assert (diagnosis.right, diagnosis.points, diagnosis.max_points) == (1, 1, 1)
    history = by_key(stages, "history")
    assert history.kind == "given" and len(history.items) == 3


def test_build_attempt_result(case: ClinicalCase) -> None:
    attempt = AttemptIn.model_validate({"diagnosis_text": "asthma", "confidence": 5})
    score = score_attempt(case, attempt)
    stats = CohortStats(
        percentile=12.5,
        cohort_size=9,
        cohort_is_simulated=True,
        histogram=[HistogramBin(points=0, count=4), HistogramBin(points=1, count=5)],
    )
    result = build_attempt_result(
        case=case, slug="s-abc123", attempt_id=42, score=score, stats=stats, pick_rates={}
    )
    assert result.attempt_id == 42 and result.case_slug == "s-abc123"
    assert (result.points, result.max_points, result.total_decisions) == (0, 3, 9)
    assert result.percentile == 12.5 and result.cohort_is_simulated is True
    assert result.final_diagnosis.name == "Pulmonary embolism"
    assert result.diagnosis.your_text == "asthma"
    assert result.diagnosis.correct is False and result.diagnosis.answered is True
    assert result.diagnosis.calibration == "overconfident"
    assert len(result.stages) == 9


# ---------- amendments: review status, reveal spoilers, hedging, benchmarks ----------


def test_llm_cases_default_to_draft_and_manual_to_approved(case_pe: dict[str, Any]) -> None:
    manual = ClinicalCase.model_validate(case_pe)
    assert default_review_status(manual) is ReviewStatus.APPROVED
    llm = ClinicalCase.model_validate({**case_pe, "source": {"kind": "llm", "provider": "gemini"}})
    assert default_review_status(llm) is ReviewStatus.DRAFT
    assert build_case_public(1, "s-abc123", llm).review_status == "draft"
    stored = build_case_public(1, "s-abc123", llm, review_status=ReviewStatus.APPROVED)
    assert stored.review_status == "approved"


def test_public_view_never_carries_source_text(case_pe: dict[str, Any]) -> None:
    source = {"kind": "llm", "text": "SECRET SOURCE NARRATIVE " * 3}
    case = ClinicalCase.model_validate({**case_pe, "source": source})
    assert "SECRET SOURCE NARRATIVE" not in build_case_public(1, "s-abc123", case).model_dump_json()


def test_reveals_that_name_the_diagnosis_are_withheld(case: ClinicalCase) -> None:
    # The contract validator blocks this at ingest; mutate after validation to prove the
    # reveal endpoint is a second line of defence (spec §6.4).
    workup = next(d for d in case.decisions if d.stage == "workup")
    workup.options[1].reveal = "Raised; in keeping with a PE."
    reveals = build_reveals(case, Stage.WORKUP, ["A", "B"])
    assert [(r.key, r.reveal) for r in reveals] == [
        ("A", "Filling defect in the right lower lobe pulmonary artery."),
        ("B", WITHHELD_TEXT),
    ]
    # The debrief (after the case closes) shows the reveal in full.
    score = score_attempt(case, AttemptIn.model_validate({"confidence": 3}))
    debrief_workup = by_key(build_debrief_stages(case, score, {}), "workup")
    assert {o.key: o.reveal for o in debrief_workup.options}["B"] == "Raised; in keeping with a PE."


def test_attempt_result_reports_hedging(case: ClinicalCase) -> None:
    attempt = AttemptIn.model_validate({"diagnosis_text": "PE or pneumonia", "confidence": 3})
    stats = CohortStats(percentile=None, cohort_size=0, cohort_is_simulated=False, histogram=[])
    result = build_attempt_result(
        case=case,
        slug="s-abc123",
        attempt_id=1,
        score=score_attempt(case, attempt),
        stats=stats,
        pick_rates={},
    )
    assert result.diagnosis.hedged is True
    assert result.diagnosis.correct is False
    assert result.benchmarks == []


def test_attempt_result_carries_benchmarks(case: ClinicalCase) -> None:
    attempt = AttemptIn.model_validate({"diagnosis_text": "PE", "confidence": 4})
    stats = CohortStats(percentile=None, cohort_size=0, cohort_is_simulated=False, histogram=[])
    bench = Benchmark(
        label="ai:claude-opus-4-8",
        provider="claude",
        model="claude-opus-4-8",
        points=3,
        max_points=3,
        diagnosis_correct=True,
        confidence=4,
        calibration=Calibration.CALIBRATED,
    )
    result = build_attempt_result(
        case=case,
        slug="s-abc123",
        attempt_id=1,
        score=score_attempt(case, attempt),
        stats=stats,
        pick_rates={},
        benchmarks=[bench],
    )
    assert result.benchmarks == [bench]
