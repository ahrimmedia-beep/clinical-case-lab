from __future__ import annotations

from app.repository.insights import merge_wrong_diagnoses


def test_wrong_diagnoses_are_grouped_by_normalized_meaning() -> None:
    rows = [
        ("Pulmonary embolism", 2),  # spelling variants of one answer collapse into one row
        ("asthma", 5),
        ("Asthma.", 3),
        ("COPD", 2),
        ("chronic obstructive pulmonary disease", 4),
        ("Birt-Hogg-Dube syndrome", 1),
    ]
    merged = merge_wrong_diagnoses(rows, limit=3)
    assert [(w.text, w.count) for w in merged] == [
        ("asthma", 8),
        ("chronic obstructive pulmonary disease", 6),
        ("Pulmonary embolism", 2),
    ]


def test_merge_keeps_the_most_common_spelling_and_drops_blanks() -> None:
    merged = merge_wrong_diagnoses([("P.E.", 1), ("PE", 3), ("  ", 4), ("?", 2)], limit=5)
    assert [(w.text, w.count) for w in merged] == [("PE", 4)]
