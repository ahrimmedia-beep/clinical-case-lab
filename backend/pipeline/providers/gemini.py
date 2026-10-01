"""Gemini on Vertex AI via google-genai (`vertexai=True`, ADC); GEMINI_API_KEY fallback for dev."""

from __future__ import annotations

import time
from typing import Any

import httpx
from google import genai
from google.auth.exceptions import GoogleAuthError
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import BaseModel, ValidationError

from app.config import Settings
from app.schemas.extract import Usage
from pipeline.pricing import cost_usd
from pipeline.providers.base import (
    InvalidOutput,
    LLMResult,
    ProviderUnavailable,
    error_for_status,
    format_validation_errors,
)

MAX_OUTPUT_TOKENS = 16_384
TIMEOUT_MS = 120_000


def make_gemini_client(settings: Settings) -> genai.Client:
    # SDK-level retries with exponential backoff on 408/429/5xx (3 attempts in total).
    http_options = types.HttpOptions(
        timeout=TIMEOUT_MS, retry_options=types.HttpRetryOptions(attempts=3)
    )
    if settings.gcp_project:
        # Vertex AI with Application Default Credentials. `vertexai=True` everywhere (spec §15);
        # never mixed with `enterprise=True`.
        return genai.Client(
            vertexai=True,
            project=settings.gcp_project,
            location=settings.gemini_location,
            http_options=http_options,
        )
    if settings.gemini_api_key:
        # Gemini Developer API: local development with synthetic data only.
        return genai.Client(
            api_key=settings.gemini_api_key.get_secret_value(), http_options=http_options
        )
    raise ProviderUnavailable(
        "Gemini is not configured: set GCP_PROJECT (Vertex AI + ADC) or GEMINI_API_KEY",
        retryable=False,
    )


class GeminiProvider:
    name = "gemini"

    def __init__(self, model: str, settings: Settings, client: Any | None = None) -> None:
        self.model = model
        self._client: Any = client if client is not None else make_gemini_client(settings)

    async def generate[T: BaseModel](
        self, *, system: str, user: str, schema: type[T]
    ) -> LLMResult[T]:
        config = types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_json_schema=schema.model_json_schema(),
            # Gemini 3 keeps its default temperature (lowering it can cause loops);
            # thinking is capped at LOW because thinking tokens are billed as output.
            thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW),
            max_output_tokens=MAX_OUTPUT_TOKENS,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        started = time.perf_counter()
        try:
            response = await self._client.aio.models.generate_content(
                model=self.model, contents=user, config=config
            )
        except genai_errors.APIError as exc:
            raise error_for_status(exc.code, exc.message or type(exc).__name__) from exc
        except GoogleAuthError as exc:
            raise ProviderUnavailable(
                f"Google credentials problem: {type(exc).__name__}", retryable=False
            ) from exc
        except httpx.TransportError as exc:
            raise ProviderUnavailable(
                f"network error calling Gemini: {type(exc).__name__}", retryable=True
            ) from exc
        latency_ms = int((time.perf_counter() - started) * 1000)
        usage = response.usage_metadata
        input_tokens = (usage.prompt_token_count or 0) if usage else 0
        output_tokens = (
            (usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0) if usage else 0
        )
        cost = cost_usd(self.name, self.model, input_tokens, output_tokens)
        spent = Usage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            latency_ms=latency_ms,
        )
        text = response.text
        if not text:
            raise InvalidOutput("the model returned an empty response", spent)
        try:
            parsed = schema.model_validate_json(text)
        except ValidationError as exc:
            raise InvalidOutput(format_validation_errors(exc), spent) from exc
        return LLMResult(
            parsed=parsed,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            cost_usd=cost,
            model=self.model,
        )
