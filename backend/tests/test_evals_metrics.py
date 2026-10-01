from __future__ import annotations

from typing import Any

import pytest

from app.schemas.case import Measurement
from evals.metrics import (
    FINDING_MATCH,
    PRF,
    chief_complaint_score,
    diagnosis_correct,
    finding_similarity,
    match_findings,
    match_measurements,
    negation_errors,
    percentile,
    unit_key,
    value_matches,
)


def m(
    name: str,
    value: float | None = None,
    unit: str | None = None,
    value_text: str | None = None,
    **extra: Any,
) -> Measurement:
    return Measurement.model_validate(
        {
            "kind": "lab",
            "name": name,
            "value": value,
            "unit": unit,
            "value_text": value_text,
            **extra,
        }
    )


def test_prf_edge_cases() -> None:
    assert (PRF(0, 0, 0).precision, PRF(0, 0, 0).recall, PRF(0, 0, 0).f1) == (1.0, 1.0, 1.0)
    assert (PRF(0, 0, 3).precision, PRF(0, 0, 3).f1) == (0.0, 0.0)
    assert (PRF(0, 2, 0).recall, PRF(0, 2, 0).f1) == (0.0, 0.0)
    combined = PRF(2, 3, 4) + PRF(1, 1, 2)
    assert combined == PRF(3, 4, 6)
    assert combined.f1 == pytest.approx(2 * 0.75 * 0.5 / 1.25)


def test_findings_greedy_one_to_one_fuzzy() -> None:
    pred = [
        "Progressive exertional dyspnea for two years",
        "Left calf swollen and tender",
        "Swollen tender left calf",
    ]
    gold = ["Progressive dyspnea on exertion for 2 years", "Swollen, tender left calf"]
    # word order and small wording changes match; the closer prediction takes the gold item
    # and the other one cannot take it a second time
    assert match_findings(pred, gold) == [(0, 0), (2, 1)]
    assert match_findings([], gold) == [] and match_findings(pred, []) == []


@pytest.mark.parametrize(
    ("pred", "gold"),
    [
        ("cough", "cough with blood-streaked sputum"),
        ("cough with blood-streaked sputum", "cough"),
        ("Cough", "Dry cough"),
        ("Dyspnea", "Progressive dyspnea on exertion for 2 years"),
    ],
)
def test_findings_matcher_is_token_sort_not_token_set(pred: str, gold: str) -> None:
    # token_set_ratio scores a subset as 100; a finding that drops (or adds) the clinically
    # important qualifier is a different finding
    assert FINDING_MATCH == 85.0
    assert finding_similarity(pred, gold) < FINDING_MATCH
    assert match_findings([pred], [gold]) == []


def test_chief_complaint_and_diagnosis_matchers() -> None:
    assert (
        chief_complaint_score(
            "sudden SOB and right-sided chest pain",
            "Sudden shortness of breath and right-sided chest pain",
        )
        == 1.0
    )
    assert chief_complaint_score("Fatigue", "Recurrent pneumothorax") == 0.0
    aliases = ["LAM", "Sporadic LAM"]
    assert diagnosis_correct("Lymphangioleiomyomatosis (LAM)", "Lymphangioleiomyomatosis", aliases)
    assert diagnosis_correct("lam", "Lymphangioleiomyomatosis", aliases)
    # word order does not matter, extra qualifiers need an alias
    assert diagnosis_correct(
        "Lymphangioleiomyomatosis, sporadic",
        "Lymphangioleiomyomatosis",
        ["Sporadic lymphangioleiomyomatosis"],
    )
    assert not diagnosis_correct("Lymphangioleiomyomatosis, sporadic", "Lymphangioleiomyomatosis")
    assert not diagnosis_correct("Pneumothorax", "Tension pneumothorax")
    assert not diagnosis_correct("", "Pulmonary embolism")
    assert not diagnosis_correct("Pulmonary hypertension", "Pulmonary embolism")


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("%", "% of predicted"),
        ("bpm", "beats/min"),
        ("x10^9/L", "×10⁹/L"),
        ("µg/L", "ug/L"),
        ("°C", "C"),
        ("breaths per minute", "/min"),
        ("", None),
    ],
)
def test_unit_variants_normalize_to_the_same_key(a: str, b: str | None) -> None:
    assert unit_key(a) == unit_key(b)


def test_value_tolerance_and_text_results() -> None:
    assert value_matches(m("D-dimer", 2400, "ng/mL"), m("D-dimer", 2440, "ng/mL"))  # 1.6 %
    assert not value_matches(m("D-dimer", 2400), m("D-dimer", 2500))  # 4 %
    assert value_matches(m("Troponin I", 0.01), m("Troponin I", value_text="< 0.01"))
    assert value_matches(m("VEGF-D", value_text="1,240"), m("VEGF-D", 1240))
    assert value_matches(m("BP", value_text="128/76"), m("BP", value_text="128/76"))
    assert not value_matches(m("BP", value_text="130/80"), m("BP", value_text="128/76"))


def test_measurements_need_name_value_and_unit() -> None:
    gold = [m("SpO2", 94, "%"), m("Serum VEGF-D", 1240, "pg/mL"), m("FEV1/FVC", 0.61)]
    aliases = {"SpO2": ["Oxygen saturation"], "Serum VEGF-D": ["VEGF-D"]}
    pred = [m("Oxygen saturation", 94, "%"), m("VEGF-D", 1240, "ng/mL"), m("FEV1/FVC", 0.61)]
    assert match_measurements(pred, gold, aliases) == [(0, 0), (2, 2)]  # wrong unit on VEGF-D


def test_negation_errors_only_count_unmatched_predictions() -> None:
    pred = ["Pleuritic chest pain", "No hemoptysis", "Fever"]
    errors = negation_errors(pred, matched_pred={0}, negated=["hemoptysis", "fever", "chest pain"])
    assert errors == ["No hemoptysis", "Fever"]


def test_percentile() -> None:
    assert percentile([], 50) == 0.0
    assert percentile([100, 200, 300, 400], 50) == 250.0
    assert percentile([100, 200, 300, 400], 95) == pytest.approx(385.0)


def test_no_bootstrap_in_the_metrics() -> None:
    # 8 cases is a smoke-level harness: no confidence intervals (spec §11, WON'T)
    import evals.metrics

    assert not hasattr(evals.metrics, "bootstrap_ci")
