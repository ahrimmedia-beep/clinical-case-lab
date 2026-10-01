"""Pure projections of a ClinicalCase.

`build_case_public` is the only path from a stored case to the browser before the case closes:
it keeps prompts and option texts, drops every answer field, and withholds given-stage items
that would name the diagnosis. Reveals (`build_reveals`) go through the same redaction. The
debrief builders show everything, unredacted.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.schemas.attempt import (
    AttemptResult,
    Benchmark,
    DebriefOption,
    DebriefStage,
    DiagnosisResult,
    HistogramBin,
    RevealOut,
)
from app.schemas.case import (
    GIVEN_STAGE_CATEGORIES,
    CasePublic,
    ClinicalCase,
    Decision,
    Finding,
    Measurement,
    PublicOption,
    PublicStage,
    ReviewStatus,
    SourceKind,
    StageItem,
)
from app.scoring import AttemptScore
from app.stages import CATALOGUE, MULTI_SELECT_STAGES, Stage, StageInfo
from app.textnorm import contains_term

WITHHELD_TEXT = "Result withheld until the debrief"

PickRates = Mapping[tuple[str, str], float]


@dataclass(frozen=True)
class CohortStats:
    percentile: float | None
    cohort_size: int
    cohort_is_simulated: bool
    histogram: list[HistogramBin]


def default_review_status(case: ClinicalCase) -> ReviewStatus:
    """Ingest rule (spec §6.2): LLM-authored cases start as drafts, everything else is approved."""
    if case.source is not None and case.source.kind is SourceKind.LLM:
        return ReviewStatus.DRAFT
    return ReviewStatus.APPROVED


def format_value(value: float | None) -> str | None:
    if value is None:
        return None
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def _leaks(texts: Sequence[str | None], terms: Sequence[str]) -> bool:
    return any(t and contains_term(t, term) for t in texts for term in terms)


def _finding_item(finding: Finding, terms: Sequence[str]) -> StageItem:
    category = finding.category.value
    if _leaks([finding.text], terms):
        return StageItem(kind="finding", category=category, text=WITHHELD_TEXT, withheld=True)
    return StageItem(kind="finding", category=category, text=finding.text)


def _measurement_item(measurement: Measurement, terms: Sequence[str]) -> StageItem:
    category = measurement.kind.value
    if _leaks([measurement.name, measurement.value_text], terms):
        return StageItem(kind="measurement", category=category, text=WITHHELD_TEXT, withheld=True)
    value = (
        format_value(measurement.value) if measurement.value is not None else measurement.value_text
    )
    return StageItem(
        kind="measurement",
        category=category,
        text=measurement.name,
        value=value,
        unit=measurement.unit,
        flag=measurement.flag,
    )


def given_items(case: ClinicalCase, stage: Stage, *, redact: bool) -> list[StageItem]:
    allowed = GIVEN_STAGE_CATEGORIES.get(stage)
    if not allowed:
        return []
    terms = case.diagnosis_terms() if redact else []
    items = [_finding_item(f, terms) for f in case.findings if f.category.value in allowed]
    items += [_measurement_item(m, terms) for m in case.measurements if m.kind.value in allowed]
    return items


def decision_for(case: ClinicalCase, stage: Stage) -> Decision | None:
    return next((d for d in case.decisions if Stage(d.stage) is stage), None)


def present_stages(case: ClinicalCase) -> list[StageInfo]:
    decided = {Stage(d.stage) for d in case.decisions}
    present: list[StageInfo] = []
    for info in CATALOGUE:
        if info.kind == "decision":
            if info.key in decided:
                present.append(info)
        elif info.key is Stage.PRESENTING_COMPLAINT or given_items(case, info.key, redact=False):
            present.append(info)
    return present


def _header(info: StageInfo) -> dict[str, Any]:
    return {
        "number": info.number,
        "key": info.key,
        "label": info.label,
        "hint": info.hint,
        "kind": info.kind,
        "scored": info.scored,
    }


def build_case_public(
    case_id: int, slug: str, case: ClinicalCase, *, review_status: ReviewStatus | None = None
) -> CasePublic:
    """The pre-close view. `review_status` is the stored value; it defaults to the ingest rule."""
    stages: list[PublicStage] = []
    for info in present_stages(case):
        if info.kind == "given":
            items = given_items(case, info.key, redact=True)
            stages.append(PublicStage(**_header(info), items=items))
            continue
        decision = decision_for(case, info.key)
        if decision is None:
            continue
        multi = info.key in MULTI_SELECT_STAGES
        stages.append(
            PublicStage(
                **_header(info),
                prompt=decision.prompt,
                input="multi_select" if multi else "free_text",
                options=[PublicOption(key=o.key, text=o.text) for o in decision.options],
            )
        )
    return CasePublic(
        id=case_id,
        slug=slug,
        title=case.title,
        specialty=case.specialty,
        difficulty=case.difficulty,
        estimated_minutes=case.estimated_minutes,
        patient=case.patient,
        chief_complaint=case.chief_complaint,
        vignette=case.vignette,
        source_kind=case.source.kind if case.source else SourceKind.MANUAL,
        review_status=review_status or default_review_status(case),
        stages=stages,
    )


def build_reveals(case: ClinicalCase, stage: Stage, option_keys: Sequence[str]) -> list[RevealOut]:
    """Reveals of the chosen options only, no correctness; a reveal naming the diagnosis is
    withheld until the debrief (defence in depth behind the ingest no-leak validator)."""
    decision = decision_for(case, stage)
    if decision is None:
        return []
    wanted = set(option_keys)
    terms = case.diagnosis_terms()
    return [
        RevealOut(key=o.key, reveal=WITHHELD_TEXT if _leaks([o.reveal], terms) else o.reveal)
        for o in decision.options
        if o.key in wanted and o.reveal
    ]


def build_debrief_stages(
    case: ClinicalCase, score: AttemptScore, pick_rates: PickRates
) -> list[DebriefStage]:
    stages: list[DebriefStage] = []
    for info in present_stages(case):
        if info.kind == "given":
            items = given_items(case, info.key, redact=False)
            stages.append(DebriefStage(**_header(info), items=items))
            continue
        decision = decision_for(case, info.key)
        stage_score = score.stages.get(info.key)
        if decision is None or stage_score is None:
            continue
        by_key = {o.key: o for o in decision.options}
        options = [
            DebriefOption(
                key=mark.key,
                text=by_key[mark.key].text,
                chosen=mark.chosen,
                state=mark.state,
                is_harmful=mark.is_harmful,
                feedback=by_key[mark.key].feedback,
                reveal=by_key[mark.key].reveal,
                pick_rate=pick_rates.get((info.key.value, mark.key)),
            )
            for mark in stage_score.options
        ]
        stages.append(
            DebriefStage(
                **_header(info),
                right=stage_score.right,
                wrong=stage_score.wrong,
                missed=stage_score.missed,
                points=stage_score.points,
                max_points=stage_score.max_points,
                explanation=decision.explanation,
                options=options,
            )
        )
    return stages


def build_attempt_result(
    *,
    case: ClinicalCase,
    slug: str,
    attempt_id: int,
    score: AttemptScore,
    stats: CohortStats,
    pick_rates: PickRates,
    benchmarks: Sequence[Benchmark] = (),
) -> AttemptResult:
    return AttemptResult(
        attempt_id=attempt_id,
        case_slug=slug,
        points=score.points,
        max_points=score.max_points,
        right=score.right,
        wrong=score.wrong,
        missed=score.missed,
        harmful=score.harmful,
        total_decisions=score.total_decisions,
        percentile=stats.percentile,
        cohort_size=stats.cohort_size,
        cohort_is_simulated=stats.cohort_is_simulated,
        histogram=stats.histogram,
        final_diagnosis=case.final_diagnosis,
        diagnosis=DiagnosisResult(
            your_text=score.diagnosis.text,
            correct=score.diagnosis.correct,
            answered=score.diagnosis.answered,
            hedged=score.diagnosis.hedged,
            confidence=score.diagnosis.confidence,
            calibration=score.diagnosis.calibration,
        ),
        stages=build_debrief_stages(case, score, pick_rates),
        benchmarks=list(benchmarks),
    )
