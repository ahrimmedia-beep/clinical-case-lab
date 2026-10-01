from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.schemas.case import CaseSource, SourceKind
from pipeline.assemble import KEYS, assemble_case, shuffled_options
from pipeline.author import AuthoringFailed, author_case
from pipeline.models import LLMAuthoredCase, LLMDecision, LLMExtractedFacts, to_extracted_facts
from pipeline.prompts import load_prompt
from pipeline.providers.fake import FIXTURES, FakeProvider

FACTS, _ = to_extracted_facts(
    LLMExtractedFacts.model_validate_json((FIXTURES / "fake_extract.json").read_text())
)
AUTHORED = LLMAuthoredCase.model_validate_json((FIXTURES / "fake_author.json").read_text())
MASKED_TEXT = "A 34-year-old woman, [NAME_1], with sudden shortness of breath."
SOURCE = CaseSource(
    kind=SourceKind.LLM,
    provider="gemini",
    model="fake-model",
    prompt_version="v1",
    text=MASKED_TEXT,
)


def leaking() -> LLMAuthoredCase:
    return AUTHORED.model_copy(update={"title": "Pulmonary embolism after a long flight"})


def leaking_reveal() -> LLMAuthoredCase:
    bad = AUTHORED.model_copy(deep=True)
    bad.decisions[2].options[0].reveal = "Filling defect consistent with pulmonary embolism."
    return bad


def option_content(decision: LLMDecision) -> set[tuple[str, bool, bool, str, str]]:
    return {(o.text, o.is_correct, o.is_harmful, o.feedback, o.reveal) for o in decision.options}


async def test_authored_case_is_a_valid_clinical_case() -> None:
    outcome = await author_case(FACTS, FakeProvider(script=[AUTHORED]), SOURCE)
    case = outcome.case
    assert outcome.attempts == 1
    assert case.source == SOURCE and case.final_diagnosis.name == "Pulmonary embolism"
    workup = next(d for d in case.decisions if d.stage == "workup")
    assert [o.key for o in workup.options] == ["A", "B", "C"]
    assert all(o.reveal for o in workup.options)
    spirometry = next(o for o in workup.options if o.text == "Spirometry")
    assert spirometry.feedback and not spirometry.is_correct
    treatment = next(d for d in case.decisions if d.stage == "treatment")
    assert all(o.reveal is None for o in treatment.options)
    assert any(o.is_harmful and not o.is_correct for o in treatment.options)
    diagnosis = next(d for d in case.decisions if d.stage == "diagnosis")
    assert diagnosis.accepted_answers[0] == "Pulmonary embolism"
    assert len(case.findings) == len(FACTS.findings)


async def test_source_carries_the_deidentified_text() -> None:
    outcome = await author_case(FACTS, FakeProvider(script=[AUTHORED]), SOURCE)
    assert outcome.case.source is not None
    assert outcome.case.source.text == MASKED_TEXT


async def test_leak_triggers_one_reask_with_the_reason() -> None:
    fake = FakeProvider(script=[leaking(), AUTHORED])
    outcome = await author_case(FACTS, fake, SOURCE)
    assert outcome.attempts == 2
    assert "title leaks the diagnosis" in fake.calls[1].user
    assert outcome.usage.output_tokens == 2 * 400


async def test_reveal_leak_triggers_a_reask_too() -> None:
    fake = FakeProvider(script=[leaking_reveal(), AUTHORED])
    outcome = await author_case(FACTS, fake, SOURCE)
    assert outcome.attempts == 2
    assert "reveal leaks the diagnosis" in fake.calls[1].user
    for decision in outcome.case.decisions:
        for option in decision.options:
            assert "embolism" not in (option.reveal or "").lower()


async def test_leak_twice_raises_authoring_failed() -> None:
    fake = FakeProvider(script=[leaking(), leaking(), AUTHORED])
    with pytest.raises(AuthoringFailed, match="2 times"):
        await author_case(FACTS, fake, SOURCE)
    assert len(fake.calls) == 2


async def test_deterministic_fixes_need_no_reask() -> None:
    sloppy = AUTHORED.model_copy(deep=True)
    sloppy.estimated_minutes = 90
    sloppy.specialty = " Pulmonology "
    sloppy.decisions[1].options[0].reveal = "should be dropped"  # reveal on differential
    sloppy.decisions[3].accepted_answers = ["PE"]  # final name gets added back
    outcome = await author_case(FACTS, FakeProvider(script=[sloppy]), SOURCE)
    case = outcome.case
    assert outcome.attempts == 1
    assert case.estimated_minutes == 30 and case.specialty == "pulmonology"
    assert all(o.reveal is None for o in case.decisions[1].options)
    assert case.decisions[3].accepted_answers == ["Pulmonary embolism", "PE"]


def test_author_prompt_forbids_spoilers_in_reveals() -> None:
    prompt = load_prompt("author")
    assert "`reveal`" in prompt.split("No spoilers")[1]


# ---------- deterministic shuffle + re-lettering (spec §6.2, amendments §D) ----------


def test_shuffle_is_deterministic_and_keeps_every_option_intact() -> None:
    for decision in AUTHORED.decisions:
        if not decision.options:
            continue
        first = shuffled_options(decision)
        again = shuffled_options(decision.model_copy(deep=True))
        assert first == again
        assert sorted(first, key=lambda o: o.text) == sorted(decision.options, key=lambda o: o.text)


def test_assembled_keys_are_relettered_in_shuffled_order() -> None:
    case_a = assemble_case(FACTS, AUTHORED, SOURCE)
    case_b = assemble_case(FACTS, AUTHORED.model_copy(deep=True), SOURCE)
    assert case_a == case_b  # same input -> same order and keys
    by_stage = {d.stage: d for d in AUTHORED.decisions}
    for decision in case_a.decisions:
        if decision.stage == "diagnosis":
            continue
        assert [o.key for o in decision.options] == list(KEYS[: len(decision.options)])
        llm = by_stage[decision.stage]
        assert {
            (o.text, o.is_correct, o.is_harmful, o.feedback or "", o.reveal or "")
            for o in decision.options
        } == option_content(llm)
        # the shuffled order is the order of shuffled_options()
        assert [o.text for o in decision.options] == [o.text for o in shuffled_options(llm)]


def test_shuffle_is_stable_across_processes() -> None:
    # The seed is sha256 of the decision JSON, not Python's per-process hash().
    code = (
        "from pipeline.assemble import shuffled_options\n"
        "from pipeline.models import LLMAuthoredCase\n"
        "from pipeline.providers.fake import FIXTURES\n"
        "a = LLMAuthoredCase.model_validate_json((FIXTURES / 'fake_author.json').read_text())\n"
        "print([[o.text for o in shuffled_options(d)] for d in a.decisions])\n"
    )
    here = [[o.text for o in shuffled_options(d)] for d in AUTHORED.decisions]
    for hash_seed in ("1", "2"):
        out = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            check=True,
            cwd=Path(__file__).resolve().parents[1],
            env={**os.environ, "PYTHONHASHSEED": hash_seed},
        )
        assert out.stdout.strip() == str(here)


def test_correct_option_is_not_always_first() -> None:
    # The LLM tends to list the right answer first; after the shuffle it must not stay there.
    firsts_correct = 0
    for n in range(20):
        decision = LLMDecision.model_validate(
            {
                "stage": "workup",
                "prompt": f"Which test do you order first? (variant {n})",
                "explanation": "The first option is the right one in the model's order.",
                "options": [
                    {
                        "text": f"Test {i} of variant {n}",
                        "is_correct": i == 0,
                        "is_harmful": False,
                        "feedback": "",
                        "reveal": "Normal.",
                    }
                    for i in range(4)
                ],
                "accepted_answers": [],
            }
        )
        firsts_correct += shuffled_options(decision)[0].is_correct
    assert firsts_correct < 20
    assert firsts_correct > 0
