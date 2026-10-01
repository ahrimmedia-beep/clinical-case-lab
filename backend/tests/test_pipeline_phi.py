from __future__ import annotations

import time

import pytest

from pipeline.phi import PhiLeakError, assert_clean, deidentify

NOTE = (
    "ED note 03/14/2026. Patient: Dana Whitfield, MRN 4471-2290, phone (617) 555-0142, "
    "e-mail dana.w@example.com, SSN 123-45-6789. Lives at 12 Oak Hill Road, Boston, MA 02115. "
    "Ms. Whitfield was seen by Dr. M. Lindqvist on March 3, 2026. Dr. Lindqvist agrees."
)


def counts(text: str) -> dict[str, int]:
    return {c.label: c.count for c in deidentify(text)[1]}


def test_masks_every_identifier_class() -> None:
    masked, _ = deidentify(NOTE)
    for secret in (
        "Dana",
        "Whitfield",
        "4471-2290",
        "555-0142",
        "example.com",
        "123-45-6789",
        "Oak Hill",
        "02115",
        "Lindqvist",
        "03/14/2026",
        "March 3, 2026",
    ):
        assert secret not in masked, secret
    assert "Patient: [NAME_1]" in masked
    assert "MRN [ID_1]" in masked
    assert "MA [ZIP_1]" in masked
    assert "Dr. [NAME_3]" in masked  # "M. Lindqvist" is one name
    assert counts(NOTE) == {
        "NAME": 4,
        "DATE": 2,
        "PHONE": 1,
        "EMAIL": 1,
        "ID": 1,
        "SSN": 1,
        "ADDRESS": 1,
        "ZIP": 1,
    }


def test_same_value_gets_the_same_placeholder() -> None:
    masked, _ = deidentify("Mr. Okafor called. Later Mr. Okafor returned.")
    assert masked == "Mr. [NAME_1] called. Later Mr. [NAME_1] returned."


def test_clinical_numbers_are_not_masked() -> None:
    text = (
        "ABG 7.32/58/61 on 2 L. BP 128/76 mmHg. WBC 14,200/uL. Platelets 250000. "
        "Budesonide/formoterol 400/12 mcg. FEV1/FVC 0.61. DLCO 48% predicted. "
        "Smoked 20 pack-years. Seen in March for follow-up."
    )
    masked, phi = deidentify(text)
    assert masked == text
    assert phi == []


def test_non_english_characters() -> None:
    text = (
        "Mrs. Núñez-García, 52, from Łódź, reports café-au-lait spots and Sjögren-like "
        "dryness. Dr. Øyvind Hansen notes: η ασθενής αναφέρει δύσπνοια."
    )
    masked, _ = deidentify(text)
    assert "Núñez" not in masked and "Øyvind" not in masked
    assert "Mrs. [NAME_1]" in masked and "Dr. [NAME_2]" in masked
    assert "café-au-lait" in masked and "Sjögren-like" in masked
    assert "η ασθενής αναφέρει δύσπνοια." in masked


def test_twenty_thousand_characters_is_fast_and_complete() -> None:
    block = "Patient: Ana Reyes, phone 617-555-0199, seen 01/02/2026. Dyspnea on exertion. "
    text = (block * (20_000 // len(block) + 1))[:20_000]
    started = time.perf_counter()
    masked, phi = deidentify(text)
    assert time.perf_counter() - started < 1.0
    assert "Reyes" not in masked and "555-0199" not in masked
    assert {c.label for c in phi} >= {"NAME", "PHONE", "DATE"}
    assert_clean(masked)


def test_assert_clean_blocks_residual_identifiers() -> None:
    with pytest.raises(PhiLeakError) as excinfo:
        assert_clean("Call me at 617-555-0142 or dana@example.com")
    assert excinfo.value.labels == ["EMAIL", "PHONE"]
    assert "617" not in str(excinfo.value)  # never echo the value
    assert_clean(deidentify(NOTE)[0])
    assert_clean("BP 128/76, ABG 7.32/58/61, FEV1 1.9 L")
