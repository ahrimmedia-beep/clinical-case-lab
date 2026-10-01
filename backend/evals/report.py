"""Score recorded model outputs against the gold set and write latest.json / latest.md.

`EvalReport` is a shared contract: the web /evals page renders latest.json (plan 03).
Do not rename keys.
"""

from __future__ import annotations

import hashlib
import statistics
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from evals.gold import GoldItem
from evals.metrics import (
    PRF,
    chief_complaint_score,
    diagnosis_correct,
    exact,
    match_findings,
    match_measurements,
    negation_errors,
    percentile,
    rate,
)
from pipeline.grounding import ground_facts
from pipeline.models import ExtractedFacts
from pipeline.phi import deidentify

MAX_NOTES = 6
SPLIT = "all"  # no dev/test split (spec §11); the key stays for the web contract

# Shown in the header of latest.md and carried in latest.json for the /evals page (spec §11).
HONESTY_NOTES: list[str] = [
    "The gold set is synthetic: 8 pulmonology case reports written for this repository; "
    "no real patient is described.",
    "Labels were drafted with an LLM before each text was written, then checked by hand and by "
    "automated consistency tests (every quote is found in the de-identified text; the labels "
    "score perfectly against themselves).",
    "8 cases is a smoke-level harness: it catches regressions and large gaps between models; "
    "it is not a benchmark, and no confidence intervals are reported.",
    "Claude helped draft the labels and is also evaluated: a known bias in its favour.",
    "Findings count only on near-identical wording (token_sort_ratio >= 85, any word order), so "
    "a paraphrase that drops a qualifier is a miss; every model is scored the same way.",
]
FAKE_NOTE = (
    "Rows with provider `fake` are a harness self-check (damaged gold labels, no model call), "
    "not a model result."
)


class Record(BaseModel):
    """One model output for one gold case: a line of evals/.cache/*.jsonl and recordings/*.jsonl."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    provider: str
    model: str
    prompt_version: str
    ok: bool
    attempts: int
    facts: ExtractedFacts | None
    error: str | None
    latency_ms: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    text_sha256: str
    recorded_at: str


# ---------- shared JSON contract (keep keys exactly) ----------


class FieldScores(BaseModel):
    patient_age: float
    patient_sex: float
    chief_complaint: float
    final_diagnosis: float
    findings_precision: float
    findings_recall: float
    findings_f1: float
    measurements_precision: float
    measurements_recall: float
    measurements_f1: float


class ModelReport(BaseModel):
    provider: str
    model: str
    cases: int
    schema_valid_rate: float
    schema_valid_first_try_rate: float
    macro_f1: float
    fields: FieldScores
    grounded_ratio: float
    hallucination_rate: float
    negation_errors: int
    latency_ms_p50: int
    latency_ms_p95: int
    cost_usd_per_case: float
    tokens_in_avg: int
    tokens_out_avg: int


class PerCase(BaseModel):
    case_id: str
    provider: str
    model: str
    findings_f1: float
    measurements_f1: float
    diagnosis_correct: bool
    grounded_ratio: float
    latency_ms: int
    cost_usd: float
    notes: list[str]


class EvalReport(BaseModel):
    generated_at: str
    prompt_version: str
    split: str
    gold_cases: int
    models: list[ModelReport]
    per_case: list[PerCase]
    honesty_notes: list[str]


# ---------- scoring ----------


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class CaseScore:
    record: Record
    age: float = 0.0
    sex: float = 0.0
    chief_complaint: float = 0.0
    diagnosis: bool = False
    findings: PRF = PRF(0, 0, 0)
    measurements: PRF = PRF(0, 0, 0)
    negation_errors: int = 0
    grounded: int = 0
    evidence_items: int = 0
    hallucinated: int = 0
    predicted_items: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def macro(self) -> float:
        parts = [
            self.age,
            self.sex,
            self.chief_complaint,
            float(self.diagnosis),
            self.findings.f1,
            self.measurements.f1,
        ]
        return statistics.fmean(parts)


def score_case(record: Record, item: GoldItem) -> CaseScore:
    gold = item.gold.facts
    score = CaseScore(record=record)
    score.findings = PRF(0, 0, len(gold.findings))
    score.measurements = PRF(0, 0, len(gold.measurements))
    if record.facts is None:
        score.notes.append(f"schema invalid: {(record.error or '')[:160]}")
        return score
    pred = record.facts
    masked, _ = deidentify(item.text)
    if record.text_sha256 != sha256(masked):
        score.notes.append("stale recording: the gold text changed after this run")

    score.age = exact(pred.patient.age_years, gold.patient.age_years)
    score.sex = exact(pred.patient.sex, gold.patient.sex)
    score.chief_complaint = chief_complaint_score(pred.chief_complaint, gold.chief_complaint)
    score.diagnosis = diagnosis_correct(
        pred.final_diagnosis.name, gold.final_diagnosis.name, item.gold.diagnosis_aliases
    )
    if not score.diagnosis:
        score.notes.append(f"diagnosis: predicted {pred.final_diagnosis.name!r}")

    pred_texts = [f.text for f in pred.findings]
    finding_pairs = match_findings(pred_texts, [f.text for f in gold.findings])
    measurement_pairs = match_measurements(
        pred.measurements, gold.measurements, item.gold.measurement_aliases
    )
    score.findings = PRF(len(finding_pairs), len(pred.findings), len(gold.findings))
    score.measurements = PRF(len(measurement_pairs), len(pred.measurements), len(gold.measurements))

    matched_findings = {i for i, _ in finding_pairs}
    matched_measurements = {i for i, _ in measurement_pairs}
    negations = negation_errors(pred_texts, matched_findings, item.gold.negated)
    score.negation_errors = len(negations)

    _, spans, _ = ground_facts(pred, masked)
    ungrounded = {s.path for s in spans if not s.grounded}
    score.grounded = sum(1 for s in spans if s.grounded)
    score.evidence_items = len(spans)
    unmatched = [f"findings[{i}]" for i in range(len(pred.findings)) if i not in matched_findings]
    unmatched += [
        f"measurements[{i}]" for i in range(len(pred.measurements)) if i not in matched_measurements
    ]
    hallucinated = [path for path in unmatched if path in ungrounded]
    score.hallucinated = len(hallucinated)
    score.predicted_items = len(pred.findings) + len(pred.measurements)

    notes = [f"negation error: {text!r}" for text in negations]
    notes += [f"hallucinated: {path}" for path in hallucinated]
    matched_gold = {j for _, j in finding_pairs}
    notes += [
        f"missed finding: {f.text!r}" for j, f in enumerate(gold.findings) if j not in matched_gold
    ]
    score.notes.extend(notes)
    score.notes = score.notes[:MAX_NOTES]
    return score


def _model_report(provider: str, model: str, scores: Sequence[CaseScore]) -> ModelReport:
    n = len(scores)
    records = [s.record for s in scores]
    findings = sum((s.findings for s in scores), PRF(0, 0, 0))
    measurements = sum((s.measurements for s in scores), PRF(0, 0, 0))
    macros = [s.macro for s in scores]
    latencies = [r.latency_ms for r in records]
    return ModelReport(
        provider=provider,
        model=model,
        cases=n,
        schema_valid_rate=round(rate(sum(r.ok for r in records), n), 4),
        schema_valid_first_try_rate=round(
            rate(sum(r.ok and r.attempts == 1 for r in records), n), 4
        ),
        macro_f1=round(statistics.fmean(macros), 4) if macros else 0.0,
        fields=FieldScores(
            patient_age=round(rate(sum(s.age for s in scores), n), 4),
            patient_sex=round(rate(sum(s.sex for s in scores), n), 4),
            chief_complaint=round(rate(sum(s.chief_complaint for s in scores), n), 4),
            final_diagnosis=round(rate(sum(s.diagnosis for s in scores), n), 4),
            findings_precision=round(findings.precision, 4),
            findings_recall=round(findings.recall, 4),
            findings_f1=round(findings.f1, 4),
            measurements_precision=round(measurements.precision, 4),
            measurements_recall=round(measurements.recall, 4),
            measurements_f1=round(measurements.f1, 4),
        ),
        grounded_ratio=round(
            rate(sum(s.grounded for s in scores), sum(s.evidence_items for s in scores)), 4
        ),
        hallucination_rate=round(
            rate(sum(s.hallucinated for s in scores), sum(s.predicted_items for s in scores)), 4
        ),
        negation_errors=sum(s.negation_errors for s in scores),
        latency_ms_p50=round(percentile(latencies, 50)),
        latency_ms_p95=round(percentile(latencies, 95)),
        cost_usd_per_case=round(rate(sum(r.cost_usd for r in records), n), 6),
        tokens_in_avg=round(rate(sum(r.input_tokens for r in records), n)),
        tokens_out_avg=round(rate(sum(r.output_tokens for r in records), n)),
    )


def build_report(
    records_by_model: dict[tuple[str, str], list[Record]],
    items: Sequence[GoldItem],
    *,
    prompt_version: str,
) -> EvalReport:
    by_id = {item.case_id: item for item in items}
    models: list[ModelReport] = []
    per_case: list[PerCase] = []
    for (provider, model), records in records_by_model.items():
        scores = [score_case(r, by_id[r.case_id]) for r in records if r.case_id in by_id]
        scores.sort(key=lambda s: s.record.case_id)
        if not scores:
            continue
        models.append(_model_report(provider, model, scores))
        for s in scores:
            per_case.append(
                PerCase(
                    case_id=s.record.case_id,
                    provider=provider,
                    model=model,
                    findings_f1=round(s.findings.f1, 4),
                    measurements_f1=round(s.measurements.f1, 4),
                    diagnosis_correct=s.diagnosis,
                    grounded_ratio=round(rate(s.grounded, s.evidence_items), 4),
                    latency_ms=s.record.latency_ms,
                    cost_usd=s.record.cost_usd,
                    notes=s.notes,
                )
            )
    notes = list(HONESTY_NOTES)
    if any(m.provider == "fake" for m in models):
        notes.append(FAKE_NOTE)
    return EvalReport(
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
        prompt_version=prompt_version,
        split=SPLIT,
        gold_cases=len(items),
        models=models,
        per_case=per_case,
        honesty_notes=notes,
    )


def to_markdown(report: EvalReport) -> str:
    lines = [
        "# Extraction eval",
        "",
        f"Generated {report.generated_at} · prompt `{report.prompt_version}` · "
        f"{report.gold_cases} gold cases, no dev/test split",
        "",
        "Read this first:",
        "",
        *[f"- {note}" for note in report.honesty_notes],
        "",
        "| Model | Valid (1st try) | Macro-F1 | Findings F1 | Measurements F1 | "
        "Diagnosis | Grounded | Hallucinated | Negation errors | p50 / p95 ms | $ / case |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for m in report.models:
        lines.append(
            f"| {m.provider}/{m.model} "
            f"| {m.schema_valid_rate:.0%} ({m.schema_valid_first_try_rate:.0%}) "
            f"| {m.macro_f1:.3f} | {m.fields.findings_f1:.3f} "
            f"| {m.fields.measurements_f1:.3f} | {m.fields.final_diagnosis:.0%} "
            f"| {m.grounded_ratio:.0%} | {m.hallucination_rate:.1%} | {m.negation_errors} "
            f"| {m.latency_ms_p50} / {m.latency_ms_p95} | {m.cost_usd_per_case:.4f} |"
        )
    lines += [
        "",
        "Macro-F1 averages six per-case scores (age, sex, chief complaint, diagnosis, findings F1, "
        "measurements F1), then averages over cases. Findings and measurements P/R/F1 are pooled "
        "over cases. Hallucinated = predicted items that match no gold item and whose evidence "
        "quote is not in the source. With eight cases, differences between models are indicative "
        "only.",
        "",
    ]
    return "\n".join(lines)


def write_report(report: EvalReport, reports_dir: Path) -> None:
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "latest.json").write_text(report.model_dump_json(indent=2) + "\n", "utf-8")
    (reports_dir / "latest.md").write_text(to_markdown(report), "utf-8")
