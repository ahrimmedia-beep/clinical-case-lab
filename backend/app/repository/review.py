"""★2 physician review gate: the full answer key plus a checklist computed server-side.

"AI-assisted, not AI-generated": an LLM-authored case is stored as a draft; a physician opens
the review, checks only the flagged items (not the whole case) and approves it. Every check is
deterministic code (no LLM): evidence grounding against the stored de-identified source text,
harmful options for explicit sign-off, the no-leak rule incl. reveals, the correct pathway,
and a PHI guard on the source text.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Text, text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.case_views import given_items, present_stages
from app.problems import raise_problem
from app.repository.cases import load_stored_case
from app.schemas.case import ClinicalCase, ReviewStatus, SourceKind
from app.schemas.review import (
    AnswerKey,
    AnswerKeyOption,
    AnswerKeyStage,
    ApproveResponse,
    CaseReview,
    CheckStatus,
    ReviewChecklistItem,
    ReviewSource,
)
from app.stages import CATALOGUE, REVEAL_STAGES, DecisionStage, Stage
from app.textnorm import contains_term
from pipeline.grounding import MAX_EVIDENCE_CHARS, locate
from pipeline.phi import PhiLeakError, assert_clean


def _item(
    check_id: str, label: str, status: CheckStatus, detail: str, items: list[str] | None = None
) -> ReviewChecklistItem:
    return ReviewChecklistItem(
        id=check_id, label=label, status=status, detail=detail, items=items or []
    )


def _evidence_items(case: ClinicalCase) -> list[tuple[str, str, str | None]]:
    """(path, what, evidence) for every fact that should be grounded; paths match the spans."""
    rows: list[tuple[str, str, str | None]] = []
    rows += [(f"findings[{i}]", f.text, f.evidence) for i, f in enumerate(case.findings)]
    rows += [(f"measurements[{i}]", m.name, m.evidence) for i, m in enumerate(case.measurements)]
    rows.append(("final_diagnosis", case.final_diagnosis.name, case.final_diagnosis.evidence))
    rows += [(f"differential[{i}]", d.name, d.evidence) for i, d in enumerate(case.differential)]
    return rows


def check_grounding(case: ClinicalCase) -> ReviewChecklistItem:
    label = "Evidence grounded in the source text"
    source = case.source.text if case.source else None
    if not source:
        return _item(
            "grounding",
            label,
            CheckStatus.WARN,
            "No source text stored (manual case): evidence cannot be re-checked.",
        )
    facts = _evidence_items(case)
    flagged: list[str] = []
    for path, what, evidence in facts:
        quote = (evidence or "").strip()
        if not quote:
            flagged.append(f'{path} "{what}": no evidence quote')
            continue
        hit = locate(quote, source)
        if hit is None or hit[1] - hit[0] > MAX_EVIDENCE_CHARS:
            flagged.append(f'{path} "{what}": evidence not found in the source text')
    if not flagged:
        return _item(
            "grounding", label, CheckStatus.OK, f"All {len(facts)} facts quote the source verbatim."
        )
    detail = f"{len(flagged)} of {len(facts)} facts are not backed by a verbatim quote."
    return _item("grounding", label, CheckStatus.WARN, detail, flagged)


def check_harmful_options(case: ClinicalCase) -> ReviewChecklistItem:
    label = "Harmful options to sign off"
    flagged = [
        f"{d.stage.value} {o.key}: {o.text}"
        for d in case.decisions
        for o in d.options
        if o.is_harmful
    ]
    if not flagged:
        return _item("harmful_options", label, CheckStatus.OK, "No option is marked harmful.")
    detail = (
        f"{len(flagged)} option(s) are marked harmful; picking one zeroes the treatment score. "
        "Confirm each is truly harmful."
    )
    return _item("harmful_options", label, CheckStatus.WARN, detail, flagged)


def find_leaks(case: ClinicalCase) -> list[str]:
    """Same rule as the ingest validator, but listing every leak instead of the first one."""
    exposed: dict[str, str] = {
        "title": case.title,
        "vignette": case.vignette,
        "chief_complaint": case.chief_complaint,
    }
    for d in case.decisions:
        exposed[f"decisions[{d.stage.value}].prompt"] = d.prompt
        if Stage(d.stage) in REVEAL_STAGES:
            for o in d.options:
                if o.reveal:
                    exposed[f"decisions[{d.stage.value}].options[{o.key}].reveal"] = o.reveal
    return [
        f"{where} names {term!r}"
        for where, value in exposed.items()
        for term in case.diagnosis_terms()
        if contains_term(value, term)
    ]


def check_no_leak(case: ClinicalCase) -> ReviewChecklistItem:
    label = "No answer before the debrief"
    leaks = find_leaks(case)
    withheld = sum(
        1
        for info in present_stages(case)
        if info.kind == "given"
        for item in given_items(case, info.key, redact=True)
        if item.withheld
    )
    hidden = f"{withheld} given-stage item(s) naming the diagnosis are withheld until the debrief."
    if leaks:
        detail = f"{len(leaks)} visible text(s) name the diagnosis. {hidden}"
        return _item("no_leak", label, CheckStatus.FAIL, detail, leaks)
    detail = f"Title, vignette, prompts and reveals do not name the diagnosis. {hidden}"
    return _item("no_leak", label, CheckStatus.OK, detail)


def check_answer_key(case: ClinicalCase) -> ReviewChecklistItem:
    label = "Answer key: confirm the pathway"
    order = [info.key for info in CATALOGUE]
    pathway: list[str] = []
    for d in sorted(case.decisions, key=lambda d: order.index(Stage(d.stage))):
        if d.stage == DecisionStage.DIAGNOSIS:
            final = case.final_diagnosis.name
            also = [a for a in d.accepted_answers if a != final]
            suffix = f" (also accepted: {', '.join(also)})" if also else ""
            pathway.append(f"diagnosis: {final}{suffix}")
            continue
        correct = "; ".join(f"{o.key} {o.text}" for o in d.options if o.is_correct)
        pathway.append(f"{d.stage.value}: {correct}")
    detail = f"{len(pathway)} decision stages; confirm the correct options form the right pathway."
    return _item("answer_key", label, CheckStatus.OK, detail, pathway)


def check_phi(case: ClinicalCase) -> ReviewChecklistItem:
    label = "No identifiers in the source text"
    source = case.source.text if case.source else None
    if not source:
        return _item("phi", label, CheckStatus.OK, "No source text stored.")
    try:
        assert_clean(source)
    except PhiLeakError as exc:
        detail = "Identifier patterns remain in the stored source text: " + ", ".join(exc.labels)
        return _item("phi", label, CheckStatus.FAIL, detail, list(exc.labels))
    return _item("phi", label, CheckStatus.OK, "No email, phone, SSN, record number or date found.")


def build_answer_key(case: ClinicalCase) -> AnswerKey:
    order = [info.key for info in CATALOGUE]
    decisions = sorted(case.decisions, key=lambda d: order.index(Stage(d.stage)))
    accepted = next((d.accepted_answers for d in decisions if d.stage == "diagnosis"), [])
    return AnswerKey(
        final_diagnosis=case.final_diagnosis,
        accepted_answers=list(accepted),
        stages=[
            AnswerKeyStage(
                stage=d.stage,
                prompt=d.prompt,
                explanation=d.explanation,
                options=[
                    AnswerKeyOption(
                        key=o.key,
                        text=o.text,
                        is_correct=o.is_correct,
                        is_harmful=o.is_harmful,
                        feedback=o.feedback,
                        reveal=o.reveal,
                    )
                    for o in d.options
                ],
            )
            for d in decisions
        ],
    )


def build_case_review(slug: str, case: ClinicalCase, review_status: ReviewStatus) -> CaseReview:
    source = case.source
    return CaseReview(
        slug=slug,
        title=case.title,
        review_status=review_status,
        source=ReviewSource(
            kind=source.kind if source else SourceKind.MANUAL,
            provider=source.provider if source else None,
            model=source.model if source else None,
            prompt_version=source.prompt_version if source else None,
        ),
        answer_key=build_answer_key(case),
        checklist=[
            check_grounding(case),
            check_harmful_options(case),
            check_no_leak(case),
            check_answer_key(case),
            check_phi(case),
        ],
    )


async def get_case_review(conn: AsyncConnection, slug: str) -> CaseReview | None:
    stored = await load_stored_case(conn, slug)
    if stored is None:
        return None
    return build_case_review(stored.slug, stored.case, stored.review_status)


APPROVE_SQL = text(
    "UPDATE cases SET review_status = 'approved', reviewed_at = now() "
    "WHERE slug = :slug AND review_status = 'draft' "
    "RETURNING slug, review_status, reviewed_at"
).columns(slug=Text, review_status=Text, reviewed_at=DateTime(timezone=True))
EXISTS_SQL = text("SELECT review_status FROM cases WHERE slug = :slug")


async def approve_case(conn: AsyncConnection, slug: str) -> ApproveResponse:
    """Draft -> approved, once. Owns its transaction. 404 unknown slug, 409 not a draft.

    The conditional UPDATE makes concurrent approvals safe: exactly one of them wins.
    """
    async with conn.begin():
        row = (await conn.execute(APPROVE_SQL, {"slug": slug})).one_or_none()
        if row is None:
            status = await conn.scalar(EXISTS_SQL, {"slug": slug})
            if status is None:
                raise_problem(404, "Case not found", f"No case with slug '{slug}'.")
            raise_problem(409, "Already approved", f"Case '{slug}' is already {status}.")
    reviewed_at: datetime = row.reviewed_at
    return ApproveResponse(
        slug=row.slug, review_status=ReviewStatus(row.review_status), reviewed_at=reviewed_at
    )
