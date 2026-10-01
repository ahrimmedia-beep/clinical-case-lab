"""The nine stages of an Eximion-style case (mirrors the debrief on eximion.com)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal


class Stage(StrEnum):
    PRESENTING_COMPLAINT = "presenting_complaint"
    HISTORY = "history"
    INTERVIEW = "interview"
    EXAMINATION = "examination"
    DIFFERENTIAL = "differential"
    WORKUP = "workup"
    RESULTS = "results"
    DIAGNOSIS = "diagnosis"
    TREATMENT = "treatment"


class DecisionStage(StrEnum):
    INTERVIEW = "interview"
    DIFFERENTIAL = "differential"
    WORKUP = "workup"
    DIAGNOSIS = "diagnosis"
    TREATMENT = "treatment"


@dataclass(frozen=True)
class StageInfo:
    number: int
    key: Stage
    label: str
    hint: str
    kind: Literal["given", "decision"]
    scored: bool


CATALOGUE: tuple[StageInfo, ...] = (
    StageInfo(
        1, Stage.PRESENTING_COMPLAINT, "Presenting complaint", "given to you", "given", False
    ),
    StageInfo(2, Stage.HISTORY, "History", "given to you", "given", False),
    StageInfo(3, Stage.INTERVIEW, "Patient interview", "questions you asked", "decision", False),
    StageInfo(4, Stage.EXAMINATION, "Examination", "given to you", "given", False),
    StageInfo(5, Stage.DIFFERENTIAL, "Differential", "entries you listed", "decision", False),
    StageInfo(6, Stage.WORKUP, "Workup", "tests you ordered", "decision", False),
    StageInfo(7, Stage.RESULTS, "Results", "given to you", "given", False),
    StageInfo(8, Stage.DIAGNOSIS, "Diagnosis", "the call you made", "decision", True),
    StageInfo(9, Stage.TREATMENT, "Treatment plan", "the plan you built", "decision", True),
)

_BY_KEY = {info.key: info for info in CATALOGUE}

MULTI_SELECT_STAGES: frozenset[Stage] = frozenset(
    {Stage.INTERVIEW, Stage.DIFFERENTIAL, Stage.WORKUP, Stage.TREATMENT}
)
REVEAL_STAGES: frozenset[Stage] = frozenset({Stage.INTERVIEW, Stage.WORKUP})
SCORED_STAGES: frozenset[Stage] = frozenset(i.key for i in CATALOGUE if i.scored)


def stage_info(key: Stage) -> StageInfo:
    return _BY_KEY[Stage(key)]
