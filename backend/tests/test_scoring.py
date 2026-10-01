from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.schemas.attempt import AttemptIn, Calibration, OptionState
from app.schemas.case import ClinicalCase
from app.scoring import (
    calibrate,
    diagnosis_candidates,
    diagnosis_matches,
    diagnosis_vocabulary,
    judge_diagnosis,
    normalize_diagnosis,
    score_attempt,
    unknown_choices,
)
from app.stages import Stage
from app.textnorm import normalize

PE_TERMS = ["Pulmonary embolism", "PE", "Pulmonary thromboembolism"]
SEED_CASES = Path(__file__).resolve().parents[1] / "seeds" / "cases"


def seed_case(name: str) -> ClinicalCase:
    return ClinicalCase.model_validate(json.loads((SEED_CASES / name).read_text()))


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


def test_attempt_input_is_capped() -> None:
    # Review Minor 2: at most 12 keys per stage (the A..L alphabet), 200 diagnosis characters.
    full = list("ABCDEFGHIJKL")
    assert AttemptIn.model_validate({"choices": {"workup": full}, "confidence": 3})
    with pytest.raises(ValidationError):
        AttemptIn.model_validate({"choices": {"workup": [*full, "A"]}, "confidence": 3})
    with pytest.raises(ValidationError):
        AttemptIn.model_validate({"diagnosis_text": "x" * 201, "confidence": 3})


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
        "pulmonary embolism, pneumothorax",
        "PE/pneumonia",
        "PE; pneumothorax",
        "PE; pneumonia",
        "PE and/or pneumonia",
        "pneumonia OR pulmonary embolism",
        "PE vs pneumothorax",
        "PE?",
        "Pulmonary embolism?",
        "pulmonary embolism or",
        # An explicit marker is a hedge even between two names of the same diagnosis.
        "PE / pulmonary embolism",
        # Lists of two diagnoses the case names.
        "PE, pneumothorax",
        "PE and pneumothorax",
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
        "Pulmonary embolism, PE",  # a comma between two names of the same diagnosis
    ],
)
def test_single_candidate_is_not_hedged(case: ClinicalCase, answer: str) -> None:
    score = score_attempt(case, attempt(dx=answer))
    assert score.diagnosis.hedged is False, answer
    assert score.diagnosis.correct is True, answer


def test_diagnosis_candidates_splits_on_every_hedge_separator() -> None:
    assert diagnosis_candidates("PE or pneumonia") == ["PE", "pneumonia"]
    assert diagnosis_candidates("a vs. b versus c, d/e; f and/or g") == list("abcdefg")
    assert diagnosis_candidates("PE?") == ["PE"]
    assert diagnosis_candidates("Lymphangioleiomyomatosis") == ["Lymphangioleiomyomatosis"]
    assert diagnosis_candidates("pulmonary embolism or") == ["pulmonary embolism"]
    assert diagnosis_candidates("") == []
    # "or" inside a word is not a separator.
    assert diagnosis_candidates("panic disorder") == ["panic disorder"]
    # Spaced dashes, "|" and line breaks separate too; a hyphen inside a name does not.
    assert diagnosis_candidates("a - b – c — d | e\nf\r\ng -- h") == list("abcdefgh")
    assert diagnosis_candidates("Alpha-1 antitrypsin deficiency") == [
        "Alpha-1 antitrypsin deficiency"
    ]
    assert diagnosis_candidates("Birt–Hogg–Dubé syndrome") == ["Birt–Hogg–Dubé syndrome"]


def test_matching_uses_token_sort_not_token_set() -> None:
    # token_set_ratio scores a superset 100; a list of guesses must not match.
    assert not diagnosis_matches("pulmonary embolism pneumonia sarcoidosis", PE_TERMS)
    assert not diagnosis_matches("pneumonia pulmonary embolism", PE_TERMS)


def test_bracketed_abbreviation_still_matches() -> None:
    assert diagnosis_matches("Pulmonary embolism (PE)", PE_TERMS)
    assert diagnosis_matches("Lymphangioleiomyomatosis (LAM)", ["Lymphangioleiomyomatosis"])


# ---------- specific diagnoses vs hedges, on the real seed cases (spec §9) ----------


def judged(case: ClinicalCase, answer: str) -> tuple[bool, bool]:
    """`(correct, hedged)` through `score_attempt`, the path every attempt takes."""
    score = score_attempt(case, attempt(dx=answer))
    return score.diagnosis.correct, score.diagnosis.hedged


@pytest.mark.parametrize(
    ("seed", "answer"),
    [
        # Marked wrong on the live site before the fix.
        (
            "03-lam.json",
            "Sporadic lymphangioleiomyomatosis (LAM) with recurrent pneumothorax and renal "
            "angiomyolipoma",
        ),
        ("02-aatd.json", "Alpha-1 antitrypsin deficiency-related panlobular emphysema"),
        (
            "02-aatd.json",
            "Alpha-1 antitrypsin deficiency (likely PiZZ) with early-onset panlobular basal "
            "emphysema",
        ),
        (
            "01-pe.json",
            "Acute pulmonary embolism secondary to deep vein thrombosis (provoked by long-haul "
            "flight and combined oral contraceptive)",
        ),
        ("03-lam.json", "sporadic LAM with recurrent pneumothorax"),
        ("02-aatd.json", "AATD-related panlobular emphysema"),
        ("01-pe.json", "acute PE secondary to DVT"),
        # More specific answers the four eval models gave.
        (
            "02-aatd.json",
            "Severe alpha-1 antitrypsin deficiency (PiZZ) with lower-lobe panlobular emphysema",
        ),
        ("03-lam.json", "Lymphangioleiomyomatosis, sporadic form"),
        # A comma followed by qualifiers, or by a clause that starts with a connector.
        ("01-pe.json", "Acute PE, provoked"),
        ("01-pe.json", "Acute PE, secondary to DVT"),
        ("01-pe.json", "Pulmonary embolism, complicated by pneumothorax"),
        ("02-aatd.json", "AATD, emphysema"),
        ("02-aatd.json", "AATD, chronic"),
        ("03-lam.json", "LAM, sporadic"),
        # The accepted name inflected inside a longer answer.
        ("01-pe.json", "Bilateral pulmonary emboli with right heart strain"),
        # A negation that follows the diagnosis is about something else.
        ("01-pe.json", "PE without right heart strain"),
        ("01-pe.json", "PE, not pneumothorax"),
        # "and" joins a co-diagnosis the case does not list as an alternative.
        ("01-pe.json", "Acute PE and DVT"),
    ],
)
def test_a_more_specific_diagnosis_is_right(seed: str, answer: str) -> None:
    assert judged(seed_case(seed), answer) == (True, False), answer


def test_a_comma_followed_by_qualifiers_is_not_a_hedge() -> None:
    assert judge_diagnosis("Sarcoidosis, Scadding stage II", ["Sarcoidosis"]) == (True, False)
    vocabulary = ["Löfgren syndrome", "Tuberculosis", "Lymphoma"]
    answer = "Sarcoidosis, Scadding stage II, presenting as Löfgren syndrome"
    assert judge_diagnosis(answer, ["Sarcoidosis"], vocabulary) == (True, False)


@pytest.mark.parametrize(
    ("seed", "answer"),
    [
        ("01-pe.json", "Acute PE, pneumothorax"),
        ("01-pe.json", "Pneumothorax, pulmonary emboli"),
        ("01-pe.json", "PE and pneumothorax"),
        ("01-pe.json", "PE & pneumothorax"),
        ("01-pe.json", "PE, GERD"),  # the case's "Gastro-oesophageal reflux" option
        ("01-pe.json", "Pneumothorax with tachycardia, pulmonary embolism"),
        ("02-aatd.json", "AATD, asthma"),
        ("02-aatd.json", "Bronchiectasis, alpha-1 antitrypsin deficiency"),
        ("02-aatd.json", "AATD, COPD"),
        ("03-lam.json", "LAM, Birt-Hogg-Dube syndrome"),
        ("03-lam.json", "Lymphangioleiomyomatosis, pulmonary Langerhans cell histiocytosis"),
        ("03-lam.json", "LAM, pneumothorax"),
        ("03-lam.json", "LAM or pneumothorax"),
        ("01-pe.json", "PE, likely pneumothorax"),  # a softener does not hide the second one
        ("01-pe.json", "Pneumothorax, PE unlikely"),
    ],
)
def test_a_comma_list_of_diagnoses_is_a_hedge(seed: str, answer: str) -> None:
    assert judged(seed_case(seed), answer) == (False, True), answer


@pytest.mark.parametrize(
    ("seed", "answer"),
    [
        # Every list separator besides the comma (review I1).
        ("01-pe.json", "PE - pneumothorax"),
        ("01-pe.json", "PE – pneumothorax"),
        ("01-pe.json", "PE — pneumothorax"),
        ("01-pe.json", "PE -- pneumothorax"),
        ("01-pe.json", "PE | pneumothorax"),
        ("01-pe.json", "PE | DVT"),  # "|" is an explicit marker, like "/"
        ("01-pe.json", "PE + pneumothorax"),
        ("01-pe.json", "PE plus pneumothorax"),
        ("01-pe.json", "PE & pneumothorax"),
        ("01-pe.json", "PE\npneumothorax"),
        ("01-pe.json", "PE\r\npneumothorax"),
        ("03-lam.json", "LAM — Birt-Hogg-Dube"),
        # No separator at all: two case diagnoses with no connector between them.
        ("01-pe.json", "PE pneumothorax"),
        ("01-pe.json", "Pulmonary embolism pneumothorax"),
        ("01-pe.json", "Pneumothorax pulmonary embolism"),
        ("01-pe.json", "Pulmonary embolism also pneumothorax"),
        ("01-pe.json", "Acute PE likely pneumothorax"),
        ("03-lam.json", "LAM BHD"),
        ("03-lam.json", "LAM Birt-Hogg-Dube"),
        ("03-lam.json", "Sporadic LAM primary spontaneous pneumothorax"),
        (
            "03-lam.json",
            "Lymphangioleiomyomatosis pulmonary langerhans cell histiocytosis pulmonary embolism "
            "birt hogg dube primary spontaneous pneumothorax",
        ),
        ("02-aatd.json", "AATD COPD"),
        ("02-aatd.json", "Alpha-1 antitrypsin deficiency asthma"),
    ],
)
def test_a_list_without_commas_is_a_hedge(seed: str, answer: str) -> None:
    assert judged(seed_case(seed), answer) == (False, True), answer


@pytest.mark.parametrize(
    ("seed", "answer"),
    [
        # The same separators in front of a qualifier, or of a diagnosis outside the case.
        ("01-pe.json", "Acute PE - provoked"),
        ("01-pe.json", "Acute PE — secondary to DVT"),
        ("01-pe.json", "Acute PE\nprovoked by the flight"),
        ("01-pe.json", "Acute PE + DVT"),
        ("01-pe.json", "PE plus DVT"),
        ("03-lam.json", "LAM – sporadic"),
        ("03-lam.json", "LAM with recurrent pneumothorax & renal angiomyolipoma"),
        ("03-lam.json", "LAM with recurrent pneumothorax plus renal angiomyolipoma"),
        # A diagnosis the case names, introduced by a connector, qualifies the answer.
        ("01-pe.json", "PE complicated by pneumothorax"),
        ("01-pe.json", "PE associated with pneumothorax and DVT"),
        ("03-lam.json", "LAM causing pneumothorax"),
        ("03-lam.json", "Pneumothorax caused by LAM"),
        # Two names of the one diagnosis, or words the vocabulary does not list.
        ("01-pe.json", "Pulmonary embolism (pulmonary thromboembolism)"),
        ("02-aatd.json", "AATD emphysema"),
        ("02-aatd.json", "Alpha-1 antitrypsin deficiency pulmonary emphysema"),
        ("02-aatd.json", "AATD in a former smoker"),
        ("03-lam.json", "Sporadic LAM recurrent pneumothorax"),
    ],
)
def test_new_separators_keep_a_specific_diagnosis_right(seed: str, answer: str) -> None:
    assert judged(seed_case(seed), answer) == (True, False), answer


def test_a_comma_list_names_the_case_vocabulary(case_pe: dict[str, Any]) -> None:
    data = copy.deepcopy(case_pe)
    data["differential"] += [{"name": "Pneumonia"}, {"name": "COPD exacerbation"}]
    case = ClinicalCase.model_validate(data)
    assert judged(case, "PE, pneumonia, COPD exacerbation") == (False, True)
    assert judged(case, "pulmonary embolism, pneumonia") == (False, True)
    assert judged(case, "Acute PE, provoked") == (True, False)


@pytest.mark.parametrize(
    ("seed", "answer"),
    [
        ("02-aatd.json", "Emphysema"),
        ("02-aatd.json", "Chronic obstructive pulmonary disease"),
        ("03-lam.json", "Pneumothorax"),
        ("03-lam.json", "Primary spontaneous pneumothorax"),
        ("01-pe.json", "Pneumothorax"),
        ("01-pe.json", "Deep vein thrombosis"),
        ("01-pe.json", "Pulmonary"),
    ],
)
def test_a_less_specific_or_other_diagnosis_is_wrong(seed: str, answer: str) -> None:
    assert judged(seed_case(seed), answer) == (False, False), answer


def test_less_specific_than_the_accepted_answer_is_wrong() -> None:
    assert judge_diagnosis("Pneumothorax", ["Tension pneumothorax"]) == (False, False)
    assert judge_diagnosis("Left tension pneumothorax", ["Tension pneumothorax"]) == (True, False)


@pytest.mark.parametrize(
    "answer",
    [
        "Not PE",
        "not pulmonary embolism",
        "No evidence of pulmonary embolism",
        "Pneumothorax with PE ruled out",
        "Pneumothorax, PE unlikely",
    ],
)
def test_a_negated_diagnosis_is_wrong(answer: str) -> None:
    correct, _ = judged(seed_case("01-pe.json"), answer)
    assert correct is False, answer


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        # A negation before the name reaches only inside its own comma part (review Minor 9).
        ("not pneumothorax, PE", (True, False)),
        ("No pneumothorax, acute PE", (True, False)),
        ("Not pneumothorax - PE", (True, False)),
        ("not pneumothorax\nPE", (True, False)),
        # Inside the part it still cancels the name; a cue right after it still counts.
        ("Not PE", (False, False)),
        ("Pneumothorax, not PE", (False, False)),
        ("PE, ruled out", (False, False)),
    ],
)
def test_negation_scope_is_the_comma_part(answer: str, expected: tuple[bool, bool]) -> None:
    assert judged(seed_case("01-pe.json"), answer) == expected, answer


def test_judge_diagnosis_without_a_vocabulary_still_works() -> None:
    assert judge_diagnosis("PE or pneumonia", PE_TERMS) == (False, True)
    assert judge_diagnosis("acute PE secondary to DVT", PE_TERMS) == (True, False)
    assert judge_diagnosis("", PE_TERMS) == (False, False)
    assert judge_diagnosis("?", PE_TERMS) == (False, False)  # blank: missed, not a hedge


def test_diagnosis_vocabulary_lists_every_diagnosis_the_case_names() -> None:
    vocabulary = diagnosis_vocabulary(seed_case("02-aatd.json"))
    for term in (
        "Alpha-1 antitrypsin deficiency",  # final diagnosis
        "AATD",  # accepted answer
        "Asthma",  # differential
        "COPD from smoking alone",  # differential decision option
        "Congestive heart failure",
    ):
        assert term in vocabulary, term
    assert len(vocabulary) == len({normalize(t) for t in vocabulary})  # no duplicates
