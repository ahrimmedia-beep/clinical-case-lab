"""The whole pipeline: de-identify -> guard -> extract -> ground -> author -> assemble."""

from __future__ import annotations

import time

import structlog

from app.schemas.case import CaseSource, SourceKind
from app.schemas.extract import ExtractResponse, Provider
from pipeline.author import author_case
from pipeline.extract import extract_facts
from pipeline.grounding import ground_facts, grounded_ratio
from pipeline.phi import assert_clean, deidentify
from pipeline.prompts import PROMPT_VERSION
from pipeline.providers.base import LLMProvider, add_usage

log = structlog.get_logger()
SOURCE_TEXT_LIMIT = 20_000  # CaseSource.text max_length


async def run_pipeline(
    text: str, provider: LLMProvider, author_provider: LLMProvider | None = None
) -> ExtractResponse:
    started = time.perf_counter()
    author = author_provider or provider
    # Trim like the API's ExtractRequest does, so span offsets, `source_text` and the case's
    # `source.text` all refer to the same string.
    masked, phi = deidentify(text.strip())
    assert_clean(masked)  # nothing identifying leaves the process

    extraction = await extract_facts(masked, provider)
    facts, spans, grounding_warnings = ground_facts(extraction.facts, masked)

    model_label = provider.model
    if author.model != provider.model:
        model_label = f"{provider.model} / {author.model}"
    warnings = extraction.warnings + grounding_warnings
    keep_text = len(masked) <= SOURCE_TEXT_LIMIT
    if not keep_text:  # placeholders can make the masked text longer than the input cap
        warnings.append("source text not stored on the case: longer than 20 000 characters")
    source = CaseSource(
        kind=SourceKind.LLM,
        provider=provider.name,
        model=model_label[:80],
        prompt_version=PROMPT_VERSION,
        text=masked if keep_text else None,  # de-identified; the review page re-checks grounding
    )
    authoring = await author_case(facts, author, source)

    usage = add_usage(extraction.usage, authoring.usage)
    usage = usage.model_copy(update={"latency_ms": int((time.perf_counter() - started) * 1000)})
    ratio = grounded_ratio(spans)
    log.info(
        "pipeline_completed",
        provider=provider.name,
        model=provider.model,
        author_model=author.model,
        prompt_version=PROMPT_VERSION,
        extract_attempts=extraction.attempts,
        author_attempts=authoring.attempts,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cost_usd=usage.cost_usd,
        latency_ms=usage.latency_ms,
        grounded_ratio=ratio,
        phi_masked=sum(p.count for p in phi),
        text_chars=len(text),
    )  # never log the text, the facts or the case
    return ExtractResponse(
        case=authoring.case,
        source_text=masked,
        spans=spans,
        phi=phi,
        grounded_ratio=ratio,
        warnings=warnings,
        provider=Provider(provider.name),
        model=provider.model,
        prompt_version=PROMPT_VERSION,
        usage=usage,
    )
