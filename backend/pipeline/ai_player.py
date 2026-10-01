"""AI player (spec §10 step 7, ★1): a model plays a stored case blinded, like a physician.

The player only ever receives `CasePublic` (no correctness, feedback, explanations, accepted
answers or reveals) and, between the turns, the reveals of the options it chose — produced by the
same server-side function as the browser's reveal endpoint. It never imports the answer-key
models, so it cannot see them by construction.

Turn 1: stages 01, 02, 04 -> option keys for interview, differential, workup.
Turn 2: + reveals of the chosen interview/workup options + stage 07 -> one diagnosis,
confidence 1-5, treatment option keys.
The result is an `AttemptIn`, scored by the same code path as a physician's attempt.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

import structlog
from pydantic import BaseModel

from app.schemas.attempt import AttemptIn, MultiSelectStage, RevealOut
from app.schemas.case import CasePublic, Patient, PublicStage, StageItem
from app.schemas.extract import Usage
from app.stages import REVEAL_STAGES, Stage
from pipeline.models import LLMPlayerTurn1, LLMPlayerTurn2
from pipeline.prompts import load_prompt, with_repair
from pipeline.providers.base import (
    InvalidOutput,
    LLMProvider,
    ProviderError,
    add_usage,
    usage_of,
)

MAX_ATTEMPTS = 2  # per turn: first try + one re-ask with the validator's errors
MAX_DIAGNOSIS_CHARS = 200  # AttemptIn.diagnosis_text
MAX_DURATION_MS = 3_600_000  # AttemptIn.duration_ms
TURN1_GIVEN = (Stage.PRESENTING_COMPLAINT, Stage.HISTORY, Stage.EXAMINATION)
TURN1_DECISIONS = (Stage.INTERVIEW, Stage.DIFFERENTIAL, Stage.WORKUP)
TURN2_DECISIONS = (Stage.DIAGNOSIS, Stage.TREATMENT)

type RevealFn = Callable[[str, Sequence[str]], Awaitable[Sequence[RevealOut]]]
log = structlog.get_logger()


@dataclass(frozen=True)
class AiPlay:
    attempt: AttemptIn
    usage: Usage  # both turns (and any re-ask): tokens, cost, summed model latency
    dropped_keys: int  # option keys the model invented or gave for an absent stage
    calls: int


class AiPlayFailed(ProviderError):
    def __init__(self, turn: int, last_errors: str, usage: Usage) -> None:
        super().__init__(
            f"the AI player's turn {turn} answer failed validation {MAX_ATTEMPTS} times"
        )
        self.last_errors = last_errors
        self.usage = usage


# ---------- rendering (only CasePublic fields) ----------


def _patient(patient: Patient) -> str:
    age = f"{patient.age_years}-year-old" if patient.age_years is not None else "age not stated"
    return f"{age}, {patient.sex.value}"


def _item(item: StageItem) -> str:
    if item.kind == "finding":
        return f"[{item.category}] {item.text}"
    parts = [f"{item.text}:" if item.value is not None else item.text]
    if item.value is not None:
        parts.append(item.value)
    if item.unit:
        parts.append(item.unit)
    if item.flag:
        parts.append(f"({item.flag.value})")
    return f"[{item.category}] " + " ".join(parts)


def _given(stage: PublicStage) -> list[str]:
    lines = [f"{stage.number:02d} {stage.label}"]
    lines += [f"- {_item(item)}" for item in stage.items] or ["- (nothing recorded)"]
    return lines


def _decision(stage: PublicStage) -> list[str]:
    lines = [f"{stage.number:02d} {stage.label} - {stage.prompt or ''}".rstrip()]
    if stage.input == "multi_select":
        lines += [f"  {o.key}. {o.text}" for o in stage.options]
    else:
        lines.append("  (free text: one diagnosis, plus your confidence from 1 to 5)")
    return lines


def _stages(case: CasePublic, keys: Sequence[Stage]) -> list[PublicStage]:
    wanted = set(keys)
    return [s for s in case.stages if Stage(s.key) in wanted]


def render_case(case: CasePublic) -> str:
    lines = [
        f"Title: {case.title}",
        f"Specialty: {case.specialty}",
        f"Patient: {_patient(case.patient)}",
        f"Chief complaint: {case.chief_complaint}",
        "",
        case.vignette,
    ]
    for stage in _stages(case, TURN1_GIVEN):
        if stage.kind == "given" and stage.items:
            lines += ["", *_given(stage)]
    return "<case>\n" + "\n".join(lines) + "\n</case>"


def render_turn1(case: CasePublic) -> str:
    lines = [render_case(case), "", "Turn 1 of 2. Decide now:"]
    for stage in _stages(case, TURN1_DECISIONS):
        lines += ["", *_decision(stage)]
    return "\n".join(lines)


def render_turn2(
    case: CasePublic,
    chosen: dict[Stage, list[str]],
    reveals: dict[Stage, Sequence[RevealOut]],
) -> str:
    lines = [render_case(case), "", "Your choices so far:"]
    for stage in _stages(case, TURN1_DECISIONS):
        keys = chosen.get(Stage(stage.key), [])
        lines.append(f"- {stage.number:02d} {stage.label}: {', '.join(keys) or 'none'}")
    lines += ["", "What you learned from them:"]
    learned: list[str] = []
    for stage in _stages(case, TURN1_DECISIONS):
        texts = {o.key: o.text for o in stage.options}
        for reveal in reveals.get(Stage(stage.key), []):
            question = texts.get(reveal.key, "")
            learned.append(f"- {stage.label} {reveal.key} ({question}): {reveal.reveal}")
    lines += learned or ["- (nothing to report)"]
    for stage in _stages(case, (Stage.RESULTS,)):
        if stage.items:
            lines += ["", *_given(stage)]
    lines += ["", "Turn 2 of 2. Decide now:"]
    for stage in _stages(case, TURN2_DECISIONS):
        lines += ["", *_decision(stage)]
    return "\n".join(lines)


# ---------- playing ----------


def clean_keys(keys: Sequence[str], valid: Sequence[str]) -> tuple[list[str], int]:
    """Keep listed keys (case-insensitive, de-duplicated, sorted); count the invented ones."""
    allowed = set(valid)
    kept: set[str] = set()
    dropped = 0
    for raw in keys:
        key = raw.strip().upper()
        if key in allowed:
            kept.add(key)
        else:
            dropped += 1
    return sorted(kept), dropped


class _Turns:
    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider
        self.system = load_prompt("player")
        self.usage = Usage()
        self.calls = 0

    async def ask[T: BaseModel](self, turn: int, user: str, schema: type[T]) -> T:
        errors: str | None = None
        for _ in range(MAX_ATTEMPTS):
            prompt = user if errors is None else with_repair(user, errors)
            self.calls += 1
            try:
                result = await self.provider.generate(
                    system=self.system, user=prompt, schema=schema
                )
            except InvalidOutput as exc:
                self.usage = add_usage(self.usage, exc.usage)
                errors = exc.errors
                continue
            self.usage = add_usage(self.usage, usage_of(result))
            return result.parsed
        raise AiPlayFailed(turn, errors or "", self.usage)


async def play_case(case: CasePublic, reveal: RevealFn, provider: LLMProvider) -> AiPlay:
    """Play `case` blinded. Raises ProviderError (incl. AiPlayFailed, ProviderUnavailable)."""
    turns = _Turns(provider)
    valid = {Stage(s.key): [o.key for o in s.options] for s in case.stages if s.kind == "decision"}
    chosen: dict[Stage, list[str]] = {}
    dropped = 0

    first = await turns.ask(1, render_turn1(case), LLMPlayerTurn1)
    answers = {
        Stage.INTERVIEW: first.interview,
        Stage.DIFFERENTIAL: first.differential,
        Stage.WORKUP: first.workup,
    }
    for stage, keys in answers.items():
        kept, lost = clean_keys(keys, valid.get(stage, []))
        dropped += lost
        if stage in valid:
            chosen[stage] = kept

    reveals: dict[Stage, Sequence[RevealOut]] = {}
    for stage in TURN1_DECISIONS:
        if stage in REVEAL_STAGES and chosen.get(stage):
            reveals[stage] = await reveal(stage.value, chosen[stage])

    second = await turns.ask(2, render_turn2(case, chosen, reveals), LLMPlayerTurn2)
    kept, lost = clean_keys(second.treatment, valid.get(Stage.TREATMENT, []))
    dropped += lost
    if Stage.TREATMENT in valid:
        chosen[Stage.TREATMENT] = kept

    diagnosis = " ".join(second.diagnosis.split())[:MAX_DIAGNOSIS_CHARS].rstrip()
    attempt = AttemptIn(
        choices={MultiSelectStage(stage.value): keys for stage, keys in chosen.items()},
        diagnosis_text=diagnosis,
        confidence=min(5, max(1, second.confidence)),
        duration_ms=min(MAX_DURATION_MS, turns.usage.latency_ms),
    )
    log.info(
        "ai_play_completed",
        provider=provider.name,
        model=provider.model,
        calls=turns.calls,
        dropped_keys=dropped,
        input_tokens=turns.usage.input_tokens,
        output_tokens=turns.usage.output_tokens,
        cost_usd=turns.usage.cost_usd,
        latency_ms=turns.usage.latency_ms,
    )  # never log the case or the answers
    return AiPlay(attempt=attempt, usage=turns.usage, dropped_keys=dropped, calls=turns.calls)
