from __future__ import annotations

from collections import Counter

import pytest
import yaml
from rapidfuzz import fuzz

from app.textnorm import contains_term, normalize
from evals.gold import GOLD_DIR, GoldItem, load_gold, load_manifest
from pipeline.grounding import locate
from pipeline.phi import assert_clean, deidentify

ITEMS = load_gold()
REQUIRED_TRAPS = (
    "negation",
    "abbreviation",
    "unit_variant",
    "distractor_history",
    "number_in_words",
)


def test_manifest_lists_all_eight_cases_once() -> None:
    manifest = load_manifest()
    ids = [entry.id for entry in manifest]
    assert len(ids) == len(set(ids)) == 8  # spec §11: 8 cases, no dev/test split
    assert {p.stem for p in GOLD_DIR.glob("*.txt")} == set(ids)
    assert {p.stem for p in GOLD_DIR.glob("*.json")} == set(ids)
    assert [item.case_id for item in load_gold()] == ids


def test_manifest_has_no_split() -> None:
    raw = yaml.safe_load((GOLD_DIR / "manifest.yaml").read_text())
    assert all(set(row) == {"id", "diagnosis"} for row in raw["cases"])


@pytest.mark.parametrize("item", ITEMS, ids=lambda item: item.case_id)
def test_identifiers_in_gold_notes_are_masked(item: GoldItem) -> None:
    masked, _ = deidentify(item.text)
    assert_clean(masked)
    for name in ("Brennan", "Okafor", "Lindqvist"):  # invented clinician names in the notes
        assert name not in masked


@pytest.mark.parametrize("item", ITEMS, ids=lambda item: item.case_id)
def test_gold_case_is_self_consistent(item: GoldItem) -> None:
    gold, facts = item.gold, item.gold.facts
    assert gold.case_id == item.case_id
    assert 150 <= len(item.text.split()) <= 600
    assert len(facts.findings) >= 8 and len(facts.measurements) >= 4 and facts.differential
    masked, _ = deidentify(item.text)
    labelled = [*facts.findings, *facts.measurements, facts.final_diagnosis, *facts.differential]
    for fact in labelled:
        assert fact.evidence, fact
        assert locate(fact.evidence, masked) is not None, (
            f"not in de-identified text: {fact.evidence!r}"
        )
    assert gold.negated, "every case needs at least one denied finding"
    for phrase in gold.negated:
        assert contains_term(item.text, phrase), f"negated phrase not in text: {phrase!r}"
        for finding in facts.findings:
            similarity = fuzz.token_set_ratio(normalize(finding.text), normalize(phrase))
            assert similarity < 80, (finding.text, phrase)
    assert set(gold.measurement_aliases) <= {m.name for m in facts.measurements}
    assert len(set(gold.traps)) >= 3


def test_traps_are_spread_across_the_set() -> None:
    counts = Counter(trap for item in ITEMS for trap in set(item.gold.traps))
    for trap in REQUIRED_TRAPS:
        assert counts[trap] >= 3, trap
    assert counts["phi"] >= 2
    diagnoses = [item.gold.facts.final_diagnosis.name for item in ITEMS]
    assert len(set(diagnoses)) == len(diagnoses)
