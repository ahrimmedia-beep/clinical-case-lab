"""Step 3: facts + authored decisions -> ClinicalCase, validated by the ingest model itself."""

from __future__ import annotations

import hashlib
import random
import string
from typing import Any

from app.schemas.case import CaseSource, ClinicalCase
from app.stages import REVEAL_STAGES, Stage
from app.textnorm import normalize
from pipeline.models import ExtractedFacts, LLMAuthoredCase, LLMDecision, LLMOption

KEYS = string.ascii_uppercase[:12]  # "A".."L", the Option.key alphabet


def shuffled_options(decision: LLMDecision) -> list[LLMOption]:
    """Options in a deterministic shuffled order (spec §6.2).

    Models tend to list the right answer first. The seed is sha256 of the decision's JSON, so
    the same authored decision always gets the same order (in every process), and keys are
    re-lettered A.. afterwards.
    """
    digest = hashlib.sha256(decision.model_dump_json().encode("utf-8")).digest()
    options = list(decision.options[: len(KEYS)])
    random.Random(int.from_bytes(digest[:8], "big")).shuffle(options)
    return options


def _accepted_answers(decision: LLMDecision, facts: ExtractedFacts) -> list[str]:
    answers: list[str] = []
    seen: set[str] = set()
    for answer in [facts.final_diagnosis.name, *decision.accepted_answers]:
        key = normalize(answer)
        if key and key not in seen:
            seen.add(key)
            answers.append(answer.strip())
    return answers[:10]


def _decision(decision: LLMDecision, facts: ExtractedFacts) -> dict[str, Any]:
    stage = Stage(decision.stage)
    if stage is Stage.DIAGNOSIS:
        options: list[dict[str, Any]] = []
        accepted = _accepted_answers(decision, facts)
    else:
        options = [
            {
                "key": KEYS[i],
                "text": o.text,
                "is_correct": o.is_correct,
                "is_harmful": o.is_harmful,
                "feedback": o.feedback.strip() or None,
                "reveal": (o.reveal.strip() or None) if stage in REVEAL_STAGES else None,
            }
            for i, o in enumerate(shuffled_options(decision))
        ]
        accepted = []
    return {
        "stage": decision.stage,
        "prompt": decision.prompt,
        "explanation": decision.explanation,
        "options": options,
        "accepted_answers": accepted,
    }


def assemble_case(
    facts: ExtractedFacts, authored: LLMAuthoredCase, source: CaseSource
) -> ClinicalCase:
    """Raises pydantic.ValidationError (incl. the no-leak rule) for the author re-ask."""
    data: dict[str, Any] = {
        "schema_version": "1.0",
        "title": authored.title,
        "specialty": authored.specialty.strip().lower() or "general medicine",
        "difficulty": authored.difficulty,
        "estimated_minutes": min(30, max(3, authored.estimated_minutes)),
        "patient": facts.patient.model_dump(mode="json"),
        "chief_complaint": authored.chief_complaint,
        "vignette": authored.vignette,
        "findings": [f.model_dump(mode="json") for f in facts.findings],
        "measurements": [m.model_dump(mode="json") for m in facts.measurements],
        "final_diagnosis": facts.final_diagnosis.model_dump(mode="json"),
        "differential": [d.model_dump(mode="json") for d in facts.differential],
        "decisions": [_decision(d, facts) for d in authored.decisions],
        "source": source.model_dump(mode="json"),
    }
    return ClinicalCase.model_validate(data)
