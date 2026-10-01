"""Pipeline data models.

Two layers:
- Domain models (`ExtractedFacts`) reuse the case contract (`app.schemas.case`) and carry every
  validation rule.
- LLM-facing models (`LLMExtractedFacts`, `LLMAuthoredCase`) are what the providers are asked to
  return. They are "Claude-safe": every field is required, absence is an explicit value ("" or
  "not_stated"), there are no numeric/length constraints, and the whole schema has at most
  16 nullable/union fields and 24 optional fields (Claude structured-output limits). The same
  schema works for Gemini `response_json_schema`.
Converters turn LLM output into domain models; a converter failure is a validation error that
the repair loop sends back to the model.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.case import Diagnosis, Finding, Measurement, Patient
from app.schemas.common import StrictModel

# ---------- domain ----------


class ExtractedFacts(StrictModel):
    """Pipeline step 1 output and the unit the eval grades (spec §6.3)."""

    patient: Patient
    chief_complaint: str = Field(min_length=3, max_length=300)
    findings: list[Finding] = Field(default_factory=list, max_length=80)
    measurements: list[Measurement] = Field(default_factory=list, max_length=80)
    final_diagnosis: Diagnosis
    differential: list[Diagnosis] = Field(default_factory=list, max_length=12)


# ---------- LLM-facing (Claude-safe) ----------

FindingCategoryLiteral = Literal[
    "symptom",
    "history",
    "medication",
    "allergy",
    "social",
    "family",
    "exam",
    "imaging",
    "procedure",
]
DecisionStageLiteral = Literal["interview", "differential", "workup", "diagnosis", "treatment"]


class LLMModel(BaseModel):
    """All LLM-facing objects forbid extra keys (`additionalProperties: false`)."""

    model_config = ConfigDict(extra="forbid")


class LLMPatient(LLMModel):
    age_years: int | None = Field(description="Age in whole years; null if the text gives none.")
    sex: Literal["female", "male", "other", "unknown"]


class LLMFinding(LLMModel):
    category: FindingCategoryLiteral
    text: str = Field(description="Short English statement of the finding, abbreviations expanded.")
    evidence: str = Field(description="Exact contiguous quote from the clinical text.")


class LLMMeasurement(LLMModel):
    kind: Literal["vital", "lab"]
    name: str = Field(description="Analyte or vital sign, e.g. 'SpO2', 'FEV1/FVC', 'D-dimer'.")
    value: float | None = Field(description="The number as written in digits; null if not numeric.")
    value_text: str = Field(
        description="Non-numeric result such as '128/76' or 'positive'; else ''."
    )
    unit: str = Field(description="Unit exactly as written; '' if none.")
    flag: Literal["low", "normal", "high", "abnormal", "not_stated"]
    evidence: str = Field(description="Exact contiguous quote from the clinical text.")


class LLMDiagnosis(LLMModel):
    name: str = Field(description="Diagnosis written out in full, not only an abbreviation.")
    icd10: str = Field(description="ICD-10-CM code if certain, e.g. 'J84.81'; else ''.")
    evidence: str = Field(description="Exact contiguous quote from the clinical text.")


class LLMExtractedFacts(LLMModel):
    patient: LLMPatient
    chief_complaint: str
    findings: list[LLMFinding]
    measurements: list[LLMMeasurement]
    final_diagnosis: LLMDiagnosis
    differential: list[LLMDiagnosis]


class LLMOption(LLMModel):
    text: str
    is_correct: bool
    is_harmful: bool
    feedback: str = Field(description="One sentence shown in the debrief; '' if none.")
    reveal: str = Field(
        description="Patient answer or test result (interview/workup only); else ''."
    )


class LLMDecision(LLMModel):
    stage: DecisionStageLiteral
    prompt: str
    explanation: str
    options: list[LLMOption] = Field(description="3-8 options; empty list for the diagnosis stage.")
    accepted_answers: list[str] = Field(description="Diagnosis stage only; empty list elsewhere.")


class LLMAuthoredCase(LLMModel):
    title: str
    specialty: str
    difficulty: Literal["easy", "medium", "hard"]
    estimated_minutes: int
    chief_complaint: str
    vignette: str
    decisions: list[LLMDecision]


# ---------- converters ----------

_ICD10 = re.compile(r"^[A-Z][0-9][0-9A-Z](\.[0-9A-Z]{1,4})?$")


def _blank_to_none(text: str) -> str | None:
    stripped = text.strip()
    return stripped or None


def _icd10(code: str, where: str, warnings: list[str]) -> str | None:
    clean = code.strip().upper()
    if not clean:
        return None
    if _ICD10.match(clean):
        return clean
    warnings.append(f"{where}.icd10 {clean!r} dropped: not an ICD-10 code")
    return None


def _diagnosis(dx: LLMDiagnosis, where: str, warnings: list[str]) -> dict[str, Any]:
    return {
        "name": dx.name,
        "icd10": _icd10(dx.icd10, where, warnings),
        "evidence": _blank_to_none(dx.evidence),
    }


def to_extracted_facts(llm: LLMExtractedFacts) -> tuple[ExtractedFacts, list[str]]:
    """LLM output -> domain facts. Raises pydantic.ValidationError if a domain rule fails."""
    warnings: list[str] = []
    data: dict[str, Any] = {
        "patient": {
            "display_name": None,
            "age_years": llm.patient.age_years,
            "sex": llm.patient.sex,
        },
        "chief_complaint": llm.chief_complaint,
        "findings": [
            {"category": f.category, "text": f.text, "evidence": _blank_to_none(f.evidence)}
            for f in llm.findings
        ],
        "measurements": [
            {
                "kind": m.kind,
                "name": m.name,
                "value": m.value,
                "value_text": _blank_to_none(m.value_text),
                "unit": _blank_to_none(m.unit),
                "flag": None if m.flag == "not_stated" else m.flag,
                "evidence": _blank_to_none(m.evidence),
            }
            for m in llm.measurements
        ],
        "final_diagnosis": _diagnosis(llm.final_diagnosis, "final_diagnosis", warnings),
        "differential": [
            _diagnosis(d, f"differential[{i}]", warnings) for i, d in enumerate(llm.differential)
        ],
    }
    return ExtractedFacts.model_validate(data), warnings


def from_extracted_facts(facts: ExtractedFacts) -> LLMExtractedFacts:
    """Domain facts -> LLM shape. Used to build fake-provider fixtures from gold labels."""

    def dx(d: Diagnosis) -> dict[str, Any]:
        return {"name": d.name, "icd10": d.icd10 or "", "evidence": d.evidence or ""}

    return LLMExtractedFacts.model_validate(
        {
            "patient": {"age_years": facts.patient.age_years, "sex": facts.patient.sex.value},
            "chief_complaint": facts.chief_complaint,
            "findings": [
                {"category": f.category.value, "text": f.text, "evidence": f.evidence or ""}
                for f in facts.findings
            ],
            "measurements": [
                {
                    "kind": m.kind.value,
                    "name": m.name,
                    "value": m.value,
                    "value_text": m.value_text or "",
                    "unit": m.unit or "",
                    "flag": m.flag.value if m.flag else "not_stated",
                    "evidence": m.evidence or "",
                }
                for m in facts.measurements
            ],
            "final_diagnosis": dx(facts.final_diagnosis),
            "differential": [dx(d) for d in facts.differential],
        }
    )
