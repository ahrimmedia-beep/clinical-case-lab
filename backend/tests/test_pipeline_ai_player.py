from __future__ import annotations

import ast
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from app.case_views import build_case_public, build_reveals
from app.schemas.attempt import RevealOut
from app.schemas.case import CasePublic, ClinicalCase
from app.stages import Stage
from pipeline import ai_player
from pipeline.ai_player import AiPlayFailed, play_case
from pipeline.models import LLMPlayerTurn1, LLMPlayerTurn2
from pipeline.providers.fake import FakeProvider

TURN1 = LLMPlayerTurn1(interview=["A", "B"], differential=["A", "B"], workup=["A"])
TURN2 = LLMPlayerTurn2(diagnosis="Pulmonary embolism", confidence=4, treatment=["A", "B"])


@pytest.fixture
def case(case_pe: dict[str, Any]) -> ClinicalCase:
    return ClinicalCase.model_validate(case_pe)


@pytest.fixture
def public(case: ClinicalCase) -> CasePublic:
    return build_case_public(7, "breathless-after-a-flight", case)


class Revealer:
    """The server side of the reveal endpoint: chosen options only, no correctness."""

    def __init__(self, case: ClinicalCase) -> None:
        self.case = case
        self.asked: list[tuple[str, list[str]]] = []

    async def __call__(self, stage: str, keys: Sequence[str]) -> list[RevealOut]:
        self.asked.append((stage, list(keys)))
        return build_reveals(self.case, Stage(stage), keys)


def prompts(fake: FakeProvider) -> list[str]:
    return [f"{call.system}\n{call.user}" for call in fake.calls]


async def test_two_turn_play_returns_an_attempt_and_usage(
    case: ClinicalCase, public: CasePublic
) -> None:
    fake = FakeProvider(name="claude", model="claude-opus-4-8", script=[TURN1, TURN2])
    play = await play_case(public, Revealer(case), fake)
    assert [c.schema for c in fake.calls] == [LLMPlayerTurn1, LLMPlayerTurn2]
    assert play.attempt.choices == {
        "interview": ["A", "B"],
        "differential": ["A", "B"],
        "workup": ["A"],
        "treatment": ["A", "B"],
    }
    assert play.attempt.diagnosis_text == "Pulmonary embolism"
    assert play.attempt.confidence == 4
    assert play.usage.input_tokens == 2 * 1200 and play.usage.output_tokens == 2 * 400
    assert play.attempt.duration_ms == play.usage.latency_ms
    assert play.calls == 2 and play.dropped_keys == 0


async def test_ai_never_sees_answers_or_reveals_of_unchosen_options(
    case: ClinicalCase, public: CasePublic
) -> None:  # amendments §D: "AI never sees is_correct / reveal of unchosen options"
    fake = FakeProvider(script=[TURN1, TURN2])
    revealer = Revealer(case)
    await play_case(public, revealer, fake)
    turn1, turn2 = prompts(fake)
    everything = turn1 + turn2
    for field in ("is_correct", "is_harmful", "accepted_answers", "explanation", "feedback"):
        assert field not in everything, field
    for decision in case.decisions:
        assert decision.explanation not in everything
        for option in decision.options:
            if option.feedback:
                assert option.feedback not in everything
    by_stage = {d.stage: d for d in case.decisions}
    chosen = {"interview": {"A", "B"}, "workup": {"A"}}
    for stage, keys in chosen.items():
        for option in by_stage[stage].options:
            assert option.reveal
            if option.key in keys:
                assert option.reveal in turn2 and option.reveal not in turn1
            elif len(option.reveal) >= 10:  # "No." could occur anywhere in prose
                assert option.reveal not in everything  # e.g. spirometry "Not performed."
    learned = turn2.split("What you learned from them:")[1].split("\n\n")[0]
    labels = [line.split(" (")[0] for line in learned.strip().splitlines()]
    label = {s.key: s.label for s in public.stages}
    interview, workup = label["interview"], label["workup"]
    assert labels == [f"- {interview} A", f"- {interview} B", f"- {workup} A"]
    assert revealer.asked == [("interview", ["A", "B"]), ("workup", ["A"])]
    for accepted in ("Pulmonary thromboembolism",):  # an accepted answer never shown anywhere
        assert accepted not in everything


async def test_turn_one_shows_given_stages_and_turn_two_adds_results(
    case: ClinicalCase, public: CasePublic
) -> None:
    fake = FakeProvider(script=[TURN1, TURN2])
    await play_case(public, Revealer(case), fake)
    turn1, turn2 = (call.user for call in fake.calls)
    assert public.vignette in turn1 and public.chief_complaint in turn1
    results = next(s for s in public.stages if s.key == "results")
    for item in results.items:
        assert item.text in turn2
    treatment = next(s for s in public.stages if s.key == "treatment")
    assert all(o.text not in turn1 for o in treatment.options)
    assert all(o.text in turn2 for o in treatment.options)
    assert "Your choices so far" in turn2


async def test_unknown_and_duplicate_keys_are_dropped_and_counted(
    case: ClinicalCase, public: CasePublic
) -> None:
    sloppy1 = LLMPlayerTurn1(interview=["A", "A", "Z"], differential=["b"], workup=["C", "K"])
    sloppy2 = LLMPlayerTurn2(diagnosis="  PE  ", confidence=3, treatment=["A", "D", "A"])
    play = await play_case(public, Revealer(case), FakeProvider(script=[sloppy1, sloppy2]))
    assert play.attempt.choices == {
        "interview": ["A"],
        "differential": ["B"],  # case-insensitive key
        "workup": ["C"],
        "treatment": ["A"],
    }
    assert play.dropped_keys == 3  # Z, K, D (duplicates are merged, not counted)
    assert play.attempt.diagnosis_text == "PE"


async def test_confidence_is_clamped_and_diagnosis_is_capped(
    case: ClinicalCase, public: CasePublic
) -> None:
    long_dx = "Pulmonary embolism " * 20
    turn2 = LLMPlayerTurn2(diagnosis=long_dx, confidence=9, treatment=[])
    play = await play_case(public, Revealer(case), FakeProvider(script=[TURN1, turn2]))
    assert play.attempt.confidence == 5
    assert len(play.attempt.diagnosis_text) <= 200
    low = LLMPlayerTurn2(diagnosis="PE", confidence=0, treatment=["A"])
    play = await play_case(public, Revealer(case), FakeProvider(script=[TURN1, low]))
    assert play.attempt.confidence == 1


async def test_invalid_output_is_reasked_once(case: ClinicalCase, public: CasePublic) -> None:
    fake = FakeProvider(script=["{", TURN1, TURN2])
    play = await play_case(public, Revealer(case), fake)
    assert play.calls == 3
    assert "rejected by the validator" in fake.calls[1].user
    with pytest.raises(AiPlayFailed, match="2 times"):
        await play_case(public, Revealer(case), FakeProvider(script=[TURN1, "{", "{"]))


async def test_stage_missing_from_the_case_is_not_played(case: ClinicalCase) -> None:
    trimmed = case.model_copy(
        update={"decisions": [d for d in case.decisions if d.stage != "interview"]}
    )
    public = build_case_public(8, "no-interview", trimmed)
    revealer = Revealer(trimmed)
    play = await play_case(public, revealer, FakeProvider(script=[TURN1, TURN2]))
    assert "interview" not in play.attempt.choices
    assert play.dropped_keys == 2  # the model still answered A, B for the absent stage
    assert revealer.asked == [("workup", ["A"])]


async def test_default_fake_provider_can_play(case: ClinicalCase, public: CasePublic) -> None:
    play = await play_case(public, Revealer(case), FakeProvider.default(name="claude"))
    assert play.attempt.diagnosis_text and play.attempt.choices["treatment"]


def test_player_module_cannot_see_the_answer_key() -> None:
    # Structural blinding: the player only ever receives CasePublic and reveal results.
    tree = ast.parse(Path(ai_player.__file__).read_text())
    names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert "ClinicalCase" not in names and "Decision" not in names and "Option" not in names


@pytest.mark.parametrize("model", [LLMPlayerTurn1, LLMPlayerTurn2])
def test_player_schemas_are_claude_safe(model: type[BaseModel]) -> None:
    schema = model.model_json_schema()
    assert set(schema["required"]) == set(schema["properties"])
    assert schema["additionalProperties"] is False
    for constraint in ("maxLength", "minLength", "maximum", "minimum", "maxItems", "anyOf"):
        assert constraint not in str(schema), constraint
