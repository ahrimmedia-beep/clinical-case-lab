"""Provider interface shared by Gemini, Claude and the fake provider."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel, ValidationError

from app.schemas.extract import Usage


@dataclass(frozen=True, slots=True)
class LLMResult[T: BaseModel]:
    parsed: T
    input_tokens: int
    output_tokens: int
    latency_ms: int
    cost_usd: float
    model: str


class LLMProvider(Protocol):
    name: str
    model: str

    async def generate[T: BaseModel](
        self, *, system: str, user: str, schema: type[T]
    ) -> LLMResult[T]: ...


class ProviderError(Exception):
    """Base class for every provider failure (maps to HTTP 502 unless a subclass says otherwise)."""


class ProviderUnavailable(ProviderError):
    """No credentials, quota exhausted, provider down or unreachable (HTTP 503).

    `retryable` is True for 429 / 5xx / network errors: the eval runner backs off and retries.
    """

    def __init__(self, message: str, *, retryable: bool, status: int | None = None) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.status = status


class InvalidOutput(ProviderError):
    """The model answered, but not with valid JSON for the schema (repairable by a re-ask)."""

    def __init__(self, errors: str, usage: Usage | None = None) -> None:
        super().__init__("model output failed schema validation")
        self.errors = errors
        self.usage = usage or Usage()  # failed calls are paid for too


def error_for_status(status: int, message: str) -> ProviderError:
    """Map an HTTP status from either SDK to our typed errors."""
    if status == 429 or status >= 500:
        return ProviderUnavailable(message, retryable=True, status=status)
    if status in (401, 403, 404):
        # bad credentials, missing IAM role, or the model is not enabled in Model Garden
        return ProviderUnavailable(message, retryable=False, status=status)
    return ProviderError(f"provider rejected the request ({status}): {message}")


def format_validation_errors(exc: ValidationError, limit: int = 20) -> str:
    """Compact "path: message" lines for a re-ask; never includes the offending input values."""
    lines = []
    for err in exc.errors()[:limit]:
        loc = ".".join(str(part) for part in err["loc"]) or "(root)"
        lines.append(f"- {loc}: {err['msg']}")
    if exc.error_count() > limit:
        lines.append(f"- ... and {exc.error_count() - limit} more")
    return "\n".join(lines)


def usage_of(result: LLMResult[Any]) -> Usage:
    return Usage(
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cost_usd=result.cost_usd,
        latency_ms=result.latency_ms,
    )


def add_usage(total: Usage, more: Usage) -> Usage:
    return Usage(
        input_tokens=total.input_tokens + more.input_tokens,
        output_tokens=total.output_tokens + more.output_tokens,
        cost_usd=round(total.cost_usd + more.cost_usd, 6),
        latency_ms=total.latency_ms + more.latency_ms,
    )
