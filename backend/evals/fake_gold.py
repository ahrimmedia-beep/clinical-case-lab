"""A fake "model" that answers with slightly damaged gold labels.

It exercises the whole harness (cache, resume, metrics, report) without network or keys, and
its committed recording gives CI a deterministic macro-F1 floor. Its numbers say nothing about
real models: the web page should label the "fake" provider as a harness self-check.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel

from evals.gold import GoldItem
from pipeline.models import LLMExtractedFacts, LLMFinding, from_extracted_facts
from pipeline.phi import deidentify
from pipeline.providers.fake import FakeProvider

MARKER_CHARS = 200


def damaged(facts: LLMExtractedFacts, n: int) -> LLMExtractedFacts:
    """Deterministic mistakes: drop the last finding; every third case adds an invented one."""
    out = facts.model_copy(deep=True)
    if out.findings:
        out.findings.pop()
    if n % 3 == 0:
        out.findings.append(
            LLMFinding(
                category="symptom",
                text="Chronic itching of both ears",
                evidence="reports chronic itching of both ears",
            )
        )
    return out


def fake_gold_provider(items: Sequence[GoldItem]) -> FakeProvider:
    answers: dict[str, LLMExtractedFacts] = {}
    for n, item in enumerate(items):
        masked, _ = deidentify(item.text)
        answers[masked[:MARKER_CHARS]] = damaged(from_extracted_facts(item.gold.facts), n)

    def lookup(user: str, schema: type[BaseModel]) -> BaseModel | None:
        if schema is not LLMExtractedFacts:
            return None
        for marker, facts in answers.items():
            if marker in user:
                return facts
        return None

    return FakeProvider(name="fake", model="fake-gold", lookup=lookup, latency_ms=40)
