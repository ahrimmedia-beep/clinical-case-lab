"""Claude on Vertex AI via AnthropicVertex (ADC), or the direct API if ANTHROPIC_API_KEY is set."""

from __future__ import annotations

import time
from typing import Any

import anthropic
from anthropic import AsyncAnthropic, AsyncAnthropicVertex
from google.auth.exceptions import GoogleAuthError
from pydantic import BaseModel, ValidationError

from app.config import Settings
from app.schemas.extract import Usage
from pipeline.pricing import cost_usd
from pipeline.providers.base import (
    InvalidOutput,
    LLMResult,
    ProviderError,
    ProviderUnavailable,
    error_for_status,
    format_validation_errors,
)

MAX_TOKENS = 16_000  # below the SDK's non-streaming limit
TIMEOUT_S = 120.0
# Every Claude call runs at low effort (spec §10): extraction and authoring are not
# reasoning-heavy, and effort is the only latency/cost lever on models that think adaptively
# (Sonnet 5, Opus 5.5). Opus 4.8 does not think because `thinking` is omitted.
OUTPUT_CONFIG: dict[str, str] = {"effort": "low"}


def make_claude_client(settings: Settings) -> AsyncAnthropic | AsyncAnthropicVertex:
    # An explicit ANTHROPIC_API_KEY wins: Vertex AI can grant a new project zero Claude quota
    # (NOT_ENOUGH_USAGE_HISTORY), and the key is only ever configured as that fallback.
    if settings.anthropic_api_key:
        return AsyncAnthropic(
            api_key=settings.anthropic_api_key.get_secret_value(),
            timeout=TIMEOUT_S,
            max_retries=2,
        )
    if settings.gcp_project:
        # Newest Claude models are served on the "global" (or "us"/"eu") Vertex endpoints only.
        return AsyncAnthropicVertex(
            project_id=settings.gcp_project,
            region=settings.claude_region,
            timeout=TIMEOUT_S,
            max_retries=2,
        )
    raise ProviderUnavailable(
        "Claude is not configured: set GCP_PROJECT (Vertex AI + ADC) or ANTHROPIC_API_KEY",
        retryable=False,
    )


def api_model_id(model: str, *, vertex: bool) -> str:
    """Vertex pins dated versions with '@' (model@YYYYMMDD); the Anthropic API uses '-'.

    The §15 models have bare IDs, so they are sent unchanged on both routes.
    """
    return model if vertex else model.replace("@", "-")


class ClaudeProvider:
    name = "claude"

    def __init__(self, model: str, settings: Settings, client: Any | None = None) -> None:
        self.model = model
        self._client: Any = client if client is not None else make_claude_client(settings)
        self._api_model = api_model_id(model, vertex=not isinstance(self._client, AsyncAnthropic))

    async def generate[T: BaseModel](
        self, *, system: str, user: str, schema: type[T]
    ) -> LLMResult[T]:
        started = time.perf_counter()
        try:
            # No temperature/top_p/top_k: Opus 5.x rejects sampling parameters. The SDK merges
            # `output_format` into `output_config.format` next to the effort setting.
            message = await self._client.messages.parse(
                model=self._api_model,
                max_tokens=MAX_TOKENS,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_format=schema,
                output_config=dict(OUTPUT_CONFIG),
            )
        except ValidationError as exc:
            # The SDK validates the JSON against `schema` while parsing; token usage is lost here.
            elapsed = int((time.perf_counter() - started) * 1000)
            raise InvalidOutput(format_validation_errors(exc), Usage(latency_ms=elapsed)) from exc
        except anthropic.APIStatusError as exc:
            raise error_for_status(exc.status_code, str(exc)) from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderUnavailable(
                f"network error calling Claude: {type(exc).__name__}", retryable=True
            ) from exc
        except GoogleAuthError as exc:
            raise ProviderUnavailable(
                f"Google credentials problem: {type(exc).__name__}", retryable=False
            ) from exc
        latency_ms = int((time.perf_counter() - started) * 1000)
        input_tokens = int(message.usage.input_tokens)
        output_tokens = int(message.usage.output_tokens)
        cost = cost_usd(self.name, self.model, input_tokens, output_tokens)
        if message.stop_reason == "refusal":
            raise ProviderError("Claude declined to process this text (stop_reason=refusal)")
        parsed = message.parsed_output
        if message.stop_reason == "max_tokens" or parsed is None:
            raise InvalidOutput(
                f"no complete JSON object (stop_reason={message.stop_reason}); answer more briefly",
                Usage(
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=cost,
                    latency_ms=latency_ms,
                ),
            )
        return LLMResult(
            parsed=parsed,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            cost_usd=cost,
            model=self.model,
        )
