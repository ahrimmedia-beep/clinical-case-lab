"""Pick a provider adapter. pricing.yaml is the model allowlist."""

from __future__ import annotations

import os

import structlog

from app.config import Settings
from app.schemas.extract import Provider
from pipeline.pricing import allowed_models, default_model
from pipeline.providers.base import LLMProvider
from pipeline.providers.claude import ClaudeProvider
from pipeline.providers.fake import FakeProvider
from pipeline.providers.gemini import GeminiProvider

FAKE_ENV = "PIPELINE_FAKE_LLM"  # "1" = deterministic fixtures, no network (tests, demos)
log = structlog.get_logger()


class UnknownModel(ValueError):
    """The requested model is not in pricing.yaml for this provider."""


def resolve_model(provider: Provider, model: str | None) -> str:
    """The model a request will run on (default filled in), without building a client.

    Raises UnknownModel for anything outside pricing.yaml. In fake mode any name is accepted.
    """
    if os.environ.get(FAKE_ENV) == "1":
        return model or f"fake-{provider.value}"
    chosen = model or default_model(provider.value)
    allowed = allowed_models(provider.value)
    if chosen not in allowed:
        raise UnknownModel(
            f"model {chosen!r} is not available for {provider.value}; "
            f"choose one of: {', '.join(allowed)}"
        )
    return chosen


def get_provider(provider: Provider, model: str | None, settings: Settings) -> LLMProvider:
    chosen = resolve_model(provider, model)
    if os.environ.get(FAKE_ENV) == "1":
        log.warning("fake_llm_provider_in_use", provider=provider.value)
        return FakeProvider.default(name=provider.value, model=chosen)
    if provider is Provider.GEMINI:
        return GeminiProvider(chosen, settings)
    return ClaudeProvider(chosen, settings)
