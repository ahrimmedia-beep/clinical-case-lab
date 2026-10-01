"""Deterministic provider for tests, CI and key-less demos (PIPELINE_FAKE_LLM=1).

Responses come from, in order: a script (consumed one per call; an Exception is raised, a str
is validated like real model text), a lookup callback, then a fixed response per schema.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ValidationError

from app.schemas.extract import Usage
from pipeline.models import LLMAuthoredCase, LLMExtractedFacts
from pipeline.providers.base import (
    InvalidOutput,
    LLMResult,
    ProviderError,
    format_validation_errors,
)

FIXTURES = Path(__file__).with_name("fixtures")
SAMPLE_TEXT_FILE = FIXTURES / "fake_source.txt"

type Scripted = BaseModel | str | Exception
type Lookup = Callable[[str, type[BaseModel]], BaseModel | None]


@dataclass(frozen=True)
class FakeCall:
    system: str
    user: str
    schema: type[BaseModel]


class FakeProvider:
    def __init__(
        self,
        *,
        name: str = "gemini",
        model: str = "fake-model",
        script: Sequence[Scripted] = (),
        by_schema: Mapping[type[BaseModel], BaseModel] | None = None,
        lookup: Lookup | None = None,
        input_tokens: int = 1200,
        output_tokens: int = 400,
        latency_ms: int = 5,
    ) -> None:
        self.name = name
        self.model = model
        self._script: list[Scripted] = list(script)
        self._by_schema = dict(by_schema or {})
        self._lookup = lookup
        self._input_tokens = input_tokens
        self._output_tokens = output_tokens
        self._latency_ms = latency_ms
        self.calls: list[FakeCall] = []

    @classmethod
    def default(cls, *, name: str = "gemini", model: str = "fake-model") -> FakeProvider:
        """Answers with the pulmonary-embolism fixtures that match `fake_source.txt`."""
        extract = (FIXTURES / "fake_extract.json").read_text(encoding="utf-8")
        author = (FIXTURES / "fake_author.json").read_text(encoding="utf-8")
        return cls(
            name=name,
            model=model,
            by_schema={
                LLMExtractedFacts: LLMExtractedFacts.model_validate_json(extract),
                LLMAuthoredCase: LLMAuthoredCase.model_validate_json(author),
            },
        )

    async def generate[T: BaseModel](
        self, *, system: str, user: str, schema: type[T]
    ) -> LLMResult[T]:
        self.calls.append(FakeCall(system=system, user=user, schema=schema))
        item = self._next(user, schema)
        if isinstance(item, Exception):
            raise item
        if isinstance(item, str):
            try:
                parsed = schema.model_validate_json(item)
            except ValidationError as exc:
                raise InvalidOutput(format_validation_errors(exc), self._usage()) from exc
        else:
            parsed = schema.model_validate(item.model_dump())
        return LLMResult(
            parsed=parsed,
            input_tokens=self._input_tokens,
            output_tokens=self._output_tokens,
            latency_ms=self._latency_ms,
            cost_usd=0.0,
            model=self.model,
        )

    def _usage(self) -> Usage:
        return Usage(
            input_tokens=self._input_tokens,
            output_tokens=self._output_tokens,
            latency_ms=self._latency_ms,
        )

    def _next(self, user: str, schema: type[BaseModel]) -> Scripted:
        if self._script:
            return self._script.pop(0)
        if self._lookup is not None:
            found = self._lookup(user, schema)
            if found is not None:
                return found
        if schema in self._by_schema:
            return self._by_schema[schema]
        raise ProviderError(f"fake provider has no response for {schema.__name__}")
