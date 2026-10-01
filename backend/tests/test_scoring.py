from __future__ import annotations

import copy
from typing import Any

import pytest

from app.schemas.attempt import AttemptIn, Calibration, OptionState
from app.schemas.case import ClinicalCase
from app.scoring import (
    calibrate,
    diagnosis_candidates,
    diagnosis_matches,
    normalize_diagnosis,
    score_attempt,
    unknown_choices,
)
from app.stages import Stage

PE_TERMS = ["Pulmonary embolism", "PE", "Pulmonary thromboembolism"]


def attempt(
    choices: dict[str, list[str]] | None = None, dx: str = "", confidence: int = 3
) -> AttemptIn:
    return AttemptIn.model_validate(
        {"choices": choices or {}, "diagnosis_text": dx, "confidence": confidence}
    )


@pytest.fixture
def case(case_pe: dict[str, Any]) -> ClinicalCase:
    return ClinicalCase.model_validate(case_pe)


PERFECT = {
    "interview": ["A", "B"],
    "differential": ["A", "B"],
    "workup": ["A", "B"],
    "treatment": ["A", "B"],
}


@pytest.mark.parametrize(
    "answer",
    [
        "Pulmonary embolism",
        "pulmonary emboli",
        "pulmonary embolus",
        "P.E.",
        "PE",
        "pe",
        "Pulmonary-embolism.",
        "PULMONARY EMBOLISM",
        "  pulmonary   embolism  ",
        "embolism, pulmonary",
        "acute pulmonary embolism",
        "Pulmonary thromboembolism",
    ],
)
def test_diagnosis_variants_match(answer: str) -> None:
    assert diagnosis_matches(answer, PE_TERMS), answer


@pytest.mark.parametrize(
    "answer",
    [
        "pulmonary",  # strictly vaguer than the key
        "embolism",
        "pneumothorax",
        "pulmonary fibrosis",
        "pulmonary hypertension",
        "deep vein thrombosis",
        "banana",
        "asdfgh",
    ],
)
def test_wrong_diagnoses_do_not_match(answer: str) -> None:
    assert not diagnosis_matches(answer, PE_TERMS), answer


def test_normalize_diagnosis_expands_abbreviations_and_initials() -> None:
    assert normalize_diagnosis("P.E.") == "pulmonary embolism"
    assert normalize_diagnosis("LAM") == "lymphangioleiomyomatosis"
    assert normalize_diagnosis("A1AT deficiency") == "alpha 1 antitrypsin deficiency"
    assert normalize_diagnosis("A.A.T.D.") == "alpha 1 antitrypsin deficiency"
    assert normalize_diagnosis("Alpha-1 antitrypsin deficiency") == "alpha 1 antitrypsin deficiency"
    assert normalize_diagnosis("vitamin b deficiency") == "vitamin b deficiency"


def test_misspelling_and_word_numbers_still_match() -> None:
    assert diagnosis_matches("lymphangioleiomyomatous", ["Lymphangioleiomyomatosis"])
    assert diagnosis_matches("alpha one antitrypsin deficiency", ["Alpha-1 antitrypsin deficiency"])


def test_empty_diagnosis_is_missed(case: ClinicalCase) -> None:
    for blank in ("", "   ", "?", "..."):
        score = score_attempt(case, attempt(dx=blank))
        dx = score.stages[Stage.DIAGNOSIS]
        assert (dx.right, dx.wrong, dx.missed) == (0, 0, 1), blank
        assert score.diagnosis.answered is False
        assert score.diagnosis.correct is False


def test_nonsense_diagnosis_is_wrong(case: ClinicalCase) -> None:
    score = score_attempt(case, attempt(dx="banana bread"))
    dx = score.stages[Stage.DIAGNOSIS]
    assert (dx.right, dx.wrong, dx.missed) == (0, 1, 0)
    assert score.diagnosis.answered is True
    assert score.points == 0


def test_multi_select_marks_right_wrong_missed_and_neutral(case: ClinicalCase) -> None:
    score = score_attempt(case, attempt({"workup": ["A", "C"]}))
    workup = score.stages[Stage.WORKUP]
    assert (workup.right, workup.wrong, workup.missed) == (1, 1, 1)
    states = {m.key: (m.chosen, m.state) for m in workup.options}
    assert states == {
        "A": (True, OptionState.RIGHT),
        "B": (False, OptionState.MISSED),
        "C": (True, OptionState.WRONG),
    }
    interview = score.stages[Stage.INTERVIEW]
    assert {m.key: m.state for m in interview.options}["C"] is OptionState.NEUTRAL
    assert workup.points == 0 and workup.max_points == 0  # unscored stage


def test_points_come_only_from_diagnosis_and_treatment(case: ClinicalCase) -> None:
    score = score_attempt(case, attempt({"treatment": ["A", "C"], "workup": ["A", "B"]}, dx="PE"))
    treatment = score.stages[Stage.TREATMENT]
    # Anti-gaming: one right minus one wrong is 0, and a harmful pick zeroes the plan anyway.
    assert (treatment.points, treatment.max_points, treatment.harmful) == (0, 2, 1)
    assert score.points == 1  # diagnosis only
    assert score.max_points == 3  # 1 + two correct treatment options
    assert score.harmful == 1
    harmful = {m.key: m.is_harmful for m in treatment.options}
    assert harmful == {"A": False, "B": False, "C": True}


def test_perfect_attempt(case: ClinicalCase) -> None:
    score = score_attempt(case, attempt(PERFECT, dx="Pulmonary embolism", confidence=5))
    assert (score.points, score.max_points) == (3, 3)
    assert (score.right, score.wrong, score.missed, score.harmful) == (9, 0, 0, 0)
    assert score.total_decisions == 9  # 2+2+2+2 correct options + the diagnosis
    assert list(score.stages) == [
        Stage.INTERVIEW,
        Stage.DIFFERENTIAL,
        Stage.WORKUP,
        Stage.DIAGNOSIS,
        Stage.TREATMENT,
    ]
    assert score.diagnosis.calibration is Calibration.CALIBRATED


def test_empty_attempt_misses_everything(case: ClinicalCase) -> None:
    score = score_attempt(case, attempt())
    assert (score.points, score.right, score.wrong, score.missed) == (0, 0, 0, 9)


def test_duplicate_keys_count_once(case: ClinicalCase) -> None:
    score = score_attempt(case, attempt({"workup": ["A", "A"]}))
    assert score.stages[Stage.WORKUP].right == 1


def test_case_without_treatment_has_one_max_point(case_pe: dict[str, Any]) -> None:
    data = copy.deepcopy(case_pe)
    data["decisions"] = [d for d in data["decisions"] if d["stage"] != "treatment"]
    score = score_attempt(ClinicalCase.model_validate(data), attempt(dx="PE"))
    assert (score.points, score.max_points) == (1, 1)


@pytest.mark.parametrize(
    ("confidence", "correct", "expected"),
    [
        (5, False, Calibration.OVERCONFIDENT),
        (4, False, Calibration.OVERCONFIDENT),
        (3, False, Calibration.CALIBRATED),
        (1, False, Calibration.CALIBRATED),
        (1, True, Calibration.UNDERCONFIDENT),
        (2, True, Calibration.UNDERCONFIDENT),
        (3, True, Calibration.CALIBRATED),
        (5, True, Calibration.CALIBRATED),
    ],
)
def test_calibration(confidence: int, correct: bool, expected: Calibration) -> None:
    assert calibrate(confidence, correct) is expected


def test_unknown_choices_names_the_bad_key_and_stage(case_pe: dict[str, Any]) -> None:
    case = ClinicalCase.model_validate(case_pe)
    problems = unknown_choices(case, attempt({"workup": ["A", "F"], "treatment": ["B"]}).choices)
    assert problems == ["option 'F' does not exist in stage 'workup'"]
    data = copy.deepcopy(case_pe)
    data["decisions"] = [d for d in data["decisions"] if d["stage"] != "interview"]
    no_interview = ClinicalCase.model_validate(data)
    problems = unknown_choices(no_interview, attempt({"interview": ["A"]}).choices)
    assert problems == ["stage 'interview' is not part of this case"]
    assert unknown_choices(case, attempt(PERFECT).choices) == []


# ---------- anti-gaming (spec §9) ----------


def _with_extra_treatment_option(case_pe: dict[str, Any]) -> ClinicalCase:
    """PE case plus a fourth, wrong-but-not-harmful treatment option D."""
    data = copy.deepcopy(case_pe)
    for decision in data["decisions"]:
        if decision["stage"] == "treatment":
            decision["options"].append(
                {"key": "D", "text": "Prescribe a cough suppressant", "is_correct": False}
            )
    return ClinicalCase.model_validate(data)


def test_select_all_treatment_scores_zero(case_pe: dict[str, Any]) -> None:
    case = _with_extra_treatment_option(case_pe)
    score = score_attempt(case, attempt({"treatment": ["A", "B", "C", "D"]}, dx="PE"))
    assert score.stages[Stage.TREATMENT].points == 0
    assert score.points == 1  # the diagnosis point only


def test_one_harmful_pick_zeroes_an_otherwise_perfect_plan(case: ClinicalCase) -> None:
    score = score_attempt(case, attempt({"treatment": ["A", "B", "C"]}, dx="PE"))
    treatment = score.stages[Stage.TREATMENT]
    assert (treatment.right, treatment.wrong, treatment.harmful) == (2, 1, 1)
    assert treatment.points == 0
    assert score.harmful == 1


def test_wrong_treatment_picks_cancel_right_ones(case_pe: dict[str, Any]) -> None:
    case = _with_extra_treatment_option(case_pe)
    two_right_one_wrong = score_attempt(case, attempt({"treatment": ["A", "B", "D"]}))
    assert two_right_one_wrong.stages[Stage.TREATMENT].points == 1
    one_right_one_wrong = score_attempt(case, attempt({"treatment": ["A", "D"]}))
    assert one_right_one_wrong.stages[Stage.TREATMENT].points == 0  # never negative


def test_harmful_picks_outside_treatment_are_reported_but_cost_no_points(
    case_pe: dict[str, Any],
) -> None:
    data = copy.deepcopy(case_pe)
    for decision in data["decisions"]:
        if decision["stage"] == "workup":
            decision["options"][2]["is_harmful"] = True  # C: spirometry, made harmful for the test
    case = ClinicalCase.model_validate(data)
    score = score_attempt(case, attempt({"workup": ["C"], "treatment": ["A", "B"]}, dx="PE"))
    assert score.harmful == 1
    assert score.stages[Stage.TREATMENT].points == 2
    assert score.points == 3


# ---------- anti-hedging (spec §9) ----------


@pytest.mark.parametrize(
    "answer",
    [
        "PE or pneumonia",
        "pulmonary embolism vs pneumothorax",
        "Pulmonary embolism versus pneumonia",
        "PE vs. pneumonia",
        "pulmonary embolism, pneumonia",
        "PE/pneumonia",
        "PE; pneumothorax",
        "PE and/or pneumonia",
        "pneumonia OR pulmonary embolism",
    ],
)
def test_hedged_diagnosis_is_wrong(case: ClinicalCase, answer: str) -> None:
    score = score_attempt(case, attempt(dx=answer, confidence=5))
    dx = score.stages[Stage.DIAGNOSIS]
    assert score.diagnosis.hedged is True, answer
    assert score.diagnosis.correct is False
    assert (dx.right, dx.wrong, dx.missed, dx.points) == (0, 1, 0, 0)
    assert score.diagnosis.calibration is Calibration.OVERCONFIDENT


@pytest.mark.parametrize(
    "answer",
    [
        "Pulmonary embolism",
        "pulmonary emboli",
        "P.E.",
        "Pulmonary-embolism.",
        "PE / pulmonary embolism",
    ],
)
def test_single_candidate_is_not_hedged(case: ClinicalCase, answer: str) -> None:
    score = score_attempt(case, attempt(dx=answer))
    assert score.diagnosis.hedged is False, answer
    assert score.diagnosis.correct is True, answer


def test_diagnosis_candidates_splits_on_every_hedge_separator() -> None:
    assert diagnosis_candidates("PE or pneumonia") == ["PE", "pneumonia"]
    assert diagnosis_candidates("a vs. b versus c, d/e; f and/or g") == list("abcdefg")
    assert diagnosis_candidates("Lymphangioleiomyomatosis") == ["Lymphangioleiomyomatosis"]
    assert diagnosis_candidates("pulmonary embolism or") == ["pulmonary embolism"]
    assert diagnosis_candidates("") == []
    # "or" inside a word is not a separator.
    assert diagnosis_candidates("panic disorder") == ["panic disorder"]


def test_matching_uses_token_sort_not_token_set() -> None:
    # token_set_ratio scores a superset 100; a list of guesses must not match.
    assert not diagnosis_matches("pulmonary embolism pneumonia sarcoidosis", PE_TERMS)
    assert not diagnosis_matches("pneumonia pulmonary embolism", PE_TERMS)


def test_bracketed_abbreviation_still_matches() -> None:
    assert diagnosis_matches("Pulmonary embolism (PE)", PE_TERMS)
    assert diagnosis_matches("Lymphangioleiomyomatosis (LAM)", ["Lymphangioleiomyomatosis"])
