from __future__ import annotations

import pytest

from evals.gold import GoldItem, load_gold
from evals.report import HONESTY_NOTES, Record, build_report, score_case, sha256, to_markdown
from pipeline.phi import deidentify

ITEMS = load_gold()


def record_for(item: GoldItem, **changes: object) -> Record:
    masked, _ = deidentify(item.text)
    data: dict[str, object] = {
        "case_id": item.case_id,
        "provider": "gold",
        "model": "gold",
        "prompt_version": "v1",
        "ok": True,
        "attempts": 1,
        "facts": item.gold.facts,
        "error": None,
        "latency_ms": 900,
        "input_tokens": 3000,
        "output_tokens": 800,
        "cost_usd": 0.01,
        "text_sha256": sha256(masked),
        "recorded_at": "2026-10-01T00:00:00+00:00",
    }
    data.update(changes)
    return Record.model_validate(data)


@pytest.mark.parametrize("item", ITEMS, ids=lambda item: item.case_id)
def test_gold_scored_against_itself_is_perfect(item: GoldItem) -> None:
    score = score_case(record_for(item), item)
    assert score.macro == 1.0, score.notes
    assert score.grounded == score.evidence_items
    assert (score.hallucinated, score.negation_errors, score.notes) == (0, 0, [])


def test_invalid_record_scores_zero_with_a_note() -> None:
    item = ITEMS[0]
    score = score_case(record_for(item, ok=False, attempts=3, facts=None, error="bad json"), item)
    assert score.macro == 0.0 and score.findings.recall == 0.0
    assert score.notes == ["schema invalid: bad json"]


def test_negated_finding_is_counted_and_noted() -> None:
    item = ITEMS[0]
    facts = item.gold.facts.model_copy(deep=True)
    negated = item.gold.negated[0]
    facts.findings.append(facts.findings[0].model_copy(update={"text": negated.capitalize()}))
    score = score_case(record_for(item, facts=facts), item)
    assert score.negation_errors == 1
    assert f"negation error: {negated.capitalize()!r}" in score.notes


def test_build_report_aggregates_and_renders_markdown() -> None:
    records = [record_for(item) for item in ITEMS]
    records[0] = record_for(ITEMS[0], ok=False, attempts=3, facts=None, error="x", latency_ms=5000)
    report = build_report({("gold", "gold"): records}, ITEMS, prompt_version="v1")
    row = report.models[0]
    assert row.cases == len(ITEMS) == report.gold_cases == 8
    assert report.split == "all"  # no dev/test split (spec §11)
    assert row.schema_valid_rate == round((len(ITEMS) - 1) / len(ITEMS), 4)
    assert row.latency_ms_p95 > row.latency_ms_p50 == 900
    assert row.cost_usd_per_case == 0.01 and row.tokens_in_avg == 3000
    assert len(report.per_case) == len(ITEMS)
    assert "| gold/gold |" in to_markdown(report)


def test_markdown_header_carries_the_honesty_notes() -> None:
    report = build_report({}, ITEMS, prompt_version="v1")
    markdown = to_markdown(report)
    header = markdown.split("| Model |")[0]
    assert report.honesty_notes == HONESTY_NOTES
    for note in HONESTY_NOTES:
        assert note in header
    text = " ".join(HONESTY_NOTES).lower()
    for point in ("synthetic", "8 cases", "not a benchmark", "drafted with an llm", "bias"):
        assert point in text, point
    assert "CI" not in markdown and "bootstrap" not in markdown.lower()
