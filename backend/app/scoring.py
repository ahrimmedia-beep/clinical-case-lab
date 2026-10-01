"""Pure scoring (spec §9). No I/O: the attempts endpoint, the cohort simulator and the AI
players all go through `score_attempt`.

Points come only from the diagnosis (1) and the treatment plan. Every other decision is marked
right / wrong / missed without points, like Eximion's debrief. Two anti-gaming rules:

* treatment points = max(0, right - wrong), and any harmful treatment pick zeroes them, so
  ticking every option scores nothing;
* a diagnosis that names several candidates ("PE or pneumonia") is wrong (`hedged`).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from rapidfuzz import fuzz

from app.schemas.attempt import AttemptIn, Calibration, MultiSelectStage, OptionState
from app.schemas.case import ClinicalCase, Decision
from app.stages import DecisionStage, Stage
from app.textnorm import normalize

FUZZY_THRESHOLD = 90

ABBREVIATIONS: dict[str, str] = {
    "pe": "pulmonary embolism",
    "lam": "lymphangioleiomyomatosis",
    "aatd": "alpha 1 antitrypsin deficiency",
    "a1atd": "alpha 1 antitrypsin deficiency",
    "a1at": "alpha 1 antitrypsin",
    "copd": "chronic obstructive pulmonary disease",
    "ipf": "idiopathic pulmonary fibrosis",
    "cap": "community acquired pneumonia",
    "abpa": "allergic bronchopulmonary aspergillosis",
    "pap": "pulmonary alveolar proteinosis",
    "dvt": "deep vein thrombosis",
    "ptx": "pneumothorax",
    "tb": "tuberculosis",
    "mi": "myocardial infarction",
    "chf": "congestive heart failure",
}

# Severity / course words that do not change the diagnosis ("acute PE" is PE). They are dropped
# from both sides before fuzzy matching; equality checks still see the full text.
QUALIFIERS: frozenset[str] = frozenset(
    {"acute", "subacute", "chronic", "massive", "submassive", "bilateral", "sporadic"}
)

# Hedging separators (spec §9): " or ", " vs ", " versus ", ",", "/", ";", "and/or".
_HEDGE_SPLIT = re.compile(r"\band/or\b|\bor\b|\bversus\b|\bvs\b\.?|[,/;]", re.IGNORECASE)


@dataclass(frozen=True)
class OptionMark:
    key: str
    chosen: bool
    state: OptionState
    is_harmful: bool


@dataclass(frozen=True)
class StageScore:
    stage: Stage
    right: int
    wrong: int
    missed: int
    harmful: int
    points: int
    max_points: int
    options: tuple[OptionMark, ...] = ()


@dataclass(frozen=True)
class DiagnosisScore:
    text: str
    answered: bool
    correct: bool
    confidence: int
    calibration: Calibration
    hedged: bool = False


@dataclass(frozen=True)
class AttemptScore:
    stages: dict[Stage, StageScore]
    diagnosis: DiagnosisScore
    points: int
    max_points: int
    right: int
    wrong: int
    missed: int
    harmful: int
    total_decisions: int


def _collapse_initials(tokens: list[str]) -> list[str]:
    """Join runs of single letters: "p e" (from "P.E.") becomes "pe"."""
    out: list[str] = []
    run: list[str] = []
    for token in [*tokens, ""]:
        if len(token) == 1 and token.isalpha():
            run.append(token)
            continue
        if run:
            out.append("".join(run))
            run = []
        if token:
            out.append(token)
    return out


def normalize_diagnosis(text: str) -> str:
    """Normalize, collapse dotted initials, expand abbreviations, drop repeated tokens.

    "Pulmonary embolism (PE)" and "pulmonary embolism" both become "pulmonary embolism".
    """
    tokens = _collapse_initials(normalize(text).split())
    expanded = " ".join(ABBREVIATIONS.get(token, token) for token in tokens).split()
    return " ".join(dict.fromkeys(expanded))


def _without_qualifiers(normalized: str) -> str:
    kept = [t for t in normalized.split() if t not in QUALIFIERS]
    return " ".join(kept) or normalized


def diagnosis_candidates(text: str) -> list[str]:
    """Split free text on the hedging separators; blank parts are dropped."""
    return [part.strip() for part in _HEDGE_SPLIT.split(text) if normalize(part)]


def diagnosis_matches(answer: str, accepted: Sequence[str]) -> bool:
    """One candidate against the accepted answers: equal after normalization, or
    `token_sort_ratio >= 90` (not `token_set_ratio`, which scores any superset 100)."""
    given = normalize_diagnosis(answer)
    if not given:
        return False
    given_core = _without_qualifiers(given)
    for candidate in accepted:
        target = normalize_diagnosis(candidate)
        if not target:
            continue
        if given == target:
            return True
        if fuzz.token_sort_ratio(given_core, _without_qualifiers(target)) >= FUZZY_THRESHOLD:
            return True
    return False


def judge_diagnosis(text: str, accepted: Sequence[str]) -> tuple[bool, bool]:
    """Return `(correct, hedged)` for a free-text diagnosis.

    An exact accepted answer always counts (even if it contains a comma). Otherwise the text is
    split on the hedging separators; more than one distinct candidate is a hedge and is wrong.
    """
    given = normalize_diagnosis(text)
    if not given:
        return False, False
    if any(given == normalize_diagnosis(a) for a in accepted):
        return True, False
    distinct = {normalize_diagnosis(c) for c in diagnosis_candidates(text)}
    if len(distinct) > 1:
        return False, True
    return diagnosis_matches(text, accepted), False


def calibrate(confidence: int, correct: bool) -> Calibration:
    if confidence >= 4 and not correct:
        return Calibration.OVERCONFIDENT
    if confidence <= 2 and correct:
        return Calibration.UNDERCONFIDENT
    return Calibration.CALIBRATED


def score_multi_select(decision: Decision, chosen: Iterable[str]) -> StageScore:
    picked = set(chosen)
    stage = Stage(decision.stage)
    right = wrong = missed = harmful = 0
    marks: list[OptionMark] = []
    for option in decision.options:
        is_chosen = option.key in picked
        if is_chosen and option.is_correct:
            state = OptionState.RIGHT
            right += 1
        elif is_chosen:
            state = OptionState.WRONG
            wrong += 1
        elif option.is_correct:
            state = OptionState.MISSED
            missed += 1
        else:
            state = OptionState.NEUTRAL
        if is_chosen and option.is_harmful:
            harmful += 1
        marks.append(OptionMark(option.key, is_chosen, state, option.is_harmful))
    scored = stage is Stage.TREATMENT
    # Anti-gaming: wrong picks cancel right ones, and one harmful pick zeroes the plan.
    points = 0 if harmful else max(0, right - wrong)
    return StageScore(
        stage=stage,
        right=right,
        wrong=wrong,
        missed=missed,
        harmful=harmful,
        points=points if scored else 0,
        max_points=sum(1 for o in decision.options if o.is_correct) if scored else 0,
        options=tuple(marks),
    )


def unknown_choices(
    case: ClinicalCase, choices: Mapping[MultiSelectStage, Sequence[str]]
) -> list[str]:
    by_stage = {Stage(d.stage): d for d in case.decisions}
    problems: list[str] = []
    for stage_key, keys in choices.items():
        decision = by_stage.get(Stage(stage_key))
        if decision is None:
            problems.append(f"stage '{stage_key}' is not part of this case")
            continue
        valid = {o.key for o in decision.options}
        for key in sorted(set(keys) - valid):
            problems.append(f"option '{key}' does not exist in stage '{stage_key}'")
    return problems


def score_attempt(case: ClinicalCase, attempt: AttemptIn) -> AttemptScore:
    chosen = {Stage(k): v for k, v in attempt.choices.items()}
    scores: dict[Stage, StageScore] = {}
    for decision in case.decisions:
        stage = Stage(decision.stage)
        if stage is not Stage.DIAGNOSIS:
            scores[stage] = score_multi_select(decision, chosen.get(stage, []))

    answered = bool(normalize(attempt.diagnosis_text))
    correct, hedged = judge_diagnosis(attempt.diagnosis_text, case.diagnosis_terms())
    diagnosis = DiagnosisScore(
        text=attempt.diagnosis_text,
        answered=answered,
        correct=correct,
        confidence=attempt.confidence,
        calibration=calibrate(attempt.confidence, correct),
        hedged=hedged,
    )
    scores[Stage.DIAGNOSIS] = StageScore(
        stage=Stage.DIAGNOSIS,
        right=int(correct),
        wrong=int(answered and not correct),
        missed=int(not answered),
        harmful=0,
        points=int(correct),
        max_points=1,
    )
    ordered = {stage: scores[stage] for stage in Stage if stage in scores}
    parts = ordered.values()
    return AttemptScore(
        stages=ordered,
        diagnosis=diagnosis,
        points=sum(s.points for s in parts),
        max_points=sum(s.max_points for s in parts),
        right=sum(s.right for s in parts),
        wrong=sum(s.wrong for s in parts),
        missed=sum(s.missed for s in parts),
        harmful=sum(s.harmful for s in parts),
        total_decisions=1
        + sum(
            1
            for d in case.decisions
            if d.stage != DecisionStage.DIAGNOSIS
            for o in d.options
            if o.is_correct
        ),
    )
