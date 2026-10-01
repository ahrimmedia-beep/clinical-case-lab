from __future__ import annotations

import time

import pytest

from pipeline.grounding import ground_facts, grounded_ratio, locate
from pipeline.models import ExtractedFacts

SOURCE = (
    "HPI: 34 y/o F with sudden-onset shortness of breath.\n"
    "She reports “sharp” right-sided chest pain —  worse on deep\n   inspiration.\n"
    "She denies hemoptysis. D-dimer 2,400 ng/mL FEU."
)


def sliced(quote: str) -> str:
    hit = locate(quote, SOURCE)
    assert hit is not None, quote
    return SOURCE[hit[0] : hit[1]]


def test_exact_quote_returns_original_offsets() -> None:
    start, end = locate("sudden-onset shortness of breath", SOURCE) or (0, 0)
    assert SOURCE[start:end] == "sudden-onset shortness of breath"


@pytest.mark.parametrize(
    ("quote", "expected"),
    [
        # whitespace differs (newline + indentation in the source)
        ("worse on deep inspiration", "worse on deep\n   inspiration"),
        # straight quotes and a plain hyphen vs curly quotes and an em dash in the source
        ('"sharp" right-sided chest pain - worse', "“sharp” right-sided chest pain —  worse"),
        # letter case
        ("SHE DENIES HEMOPTYSIS", "She denies hemoptysis"),
        # wrapping quotes and a trailing period added by the model
        ("'D-dimer 2,400 ng/mL FEU.'", "D-dimer 2,400 ng/mL FEU"),
    ],
)
def test_normalized_quotes_are_grounded_with_correct_offsets(quote: str, expected: str) -> None:
    assert sliced(quote) == expected


def test_small_transcription_slip_is_grounded_by_fuzzy_fallback() -> None:
    assert sliced("sudden onset shortnes of breath") == "sudden-onset shortness of breath"


def test_absent_or_too_short_quotes_are_not_grounded() -> None:
    assert locate("productive cough with green sputum", SOURCE) is None
    assert locate("pain", SOURCE) is None  # < 8 chars: would match anything
    assert locate("", SOURCE) is None
    assert locate("x" * 500, "short source") is None


def test_long_source_and_long_quote_stay_fast() -> None:
    filler = "Routine follow-up without new complaints. " * 480  # ~20k characters
    source = (
        filler + "Bronchoalveolar lavage returned milky, opaque fluid with PAS-positive material."
    )
    quote = "bronchoalveolar lavage returned milky opaque fluid with PAS positive material"
    started = time.perf_counter()
    hit = locate(quote, source)
    assert hit is not None and source[hit[0] :].startswith("Bronchoalveolar")
    assert locate("completely unrelated statement about the kidneys", source) is None
    assert time.perf_counter() - started < 1.0


def test_ground_facts_marks_spans_and_replaces_quotes_with_source_slices() -> None:
    facts = ExtractedFacts.model_validate(
        {
            "patient": {"age_years": 34, "sex": "female"},
            "chief_complaint": "Sudden shortness of breath",
            "findings": [
                {
                    "category": "symptom",
                    "text": "Pleuritic chest pain",
                    "evidence": "worse on deep inspiration",
                },
                {"category": "symptom", "text": "Fever", "evidence": "febrile to 39 C"},
            ],
            "measurements": [
                {
                    "kind": "lab",
                    "name": "D-dimer",
                    "value": 2400,
                    "unit": "ng/mL FEU",
                    "evidence": "d-dimer 2,400 ng/ml feu",
                },
            ],
            "final_diagnosis": {"name": "Pulmonary embolism", "evidence": None},
            "differential": [],
        }
    )
    grounded, spans, warnings = ground_facts(facts, SOURCE)
    assert [s.path for s in spans] == [
        "findings[0]",
        "findings[1]",
        "measurements[0]",
        "final_diagnosis",
    ]
    assert [s.grounded for s in spans] == [True, False, True, False]
    assert grounded.findings[0].evidence == "worse on deep\n   inspiration"
    assert grounded.measurements[0].evidence == "D-dimer 2,400 ng/mL FEU"
    assert spans[0].start is not None and SOURCE[spans[0].start : spans[0].end] == spans[0].quote
    assert warnings == [
        "findings[1]: evidence not found in the source text",
        "final_diagnosis: no evidence quote",
    ]
    assert grounded_ratio(spans) == 0.5
