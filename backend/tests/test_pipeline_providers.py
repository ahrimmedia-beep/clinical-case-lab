from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from google.genai import errors as genai_errors
from pydantic import ValidationError

from app.config import Settings
from app.schemas.extract import Provider
from pipeline.factory import UnknownModel, get_provider
from pipeline.models import LLMExtractedFacts, LLMPatient
from pipeline.pricing import cost_usd, load_pricing
from pipeline.providers import gemini as gemini_module
from pipeline.providers.base import (
    InvalidOutput,
    ProviderError,
    ProviderUnavailable,
    error_for_status,
)
from pipeline.providers.claude import ClaudeProvider, api_model_id, make_claude_client
from pipeline.providers.fake import FIXTURES, FakeProvider
from pipeline.providers.gemini import GeminiProvider, make_gemini_client

FACTS_JSON = (FIXTURES / "fake_extract.json").read_text()


def no_keys() -> Settings:
    return Settings(_env_file=None, gcp_project=None, gemini_api_key=None, anthropic_api_key=None)


@pytest.mark.parametrize(
    ("status", "kind", "retryable"),
    [
        (429, ProviderUnavailable, True),
        (500, ProviderUnavailable, True),
        (529, ProviderUnavailable, True),
        (403, ProviderUnavailable, False),
        (404, ProviderUnavailable, False),
        (400, ProviderError, None),
    ],
)
def test_error_for_status(status: int, kind: type[Exception], retryable: bool | None) -> None:
    err = error_for_status(status, "boom")
    assert type(err) is kind
    if isinstance(err, ProviderUnavailable):
        assert err.retryable is retryable and err.status == status


async def test_fake_provider_follows_its_script() -> None:
    fake = FakeProvider(script=["{not json", LLMPatient(age_years=3, sex="male")])
    with pytest.raises(InvalidOutput) as excinfo:
        await fake.generate(system="s", user="u", schema=LLMPatient)
    assert "json" in excinfo.value.errors.lower()
    ok = await fake.generate(system="s", user="u2", schema=LLMPatient)
    assert ok.parsed.age_years == 3 and ok.cost_usd == 0.0
    assert [c.user for c in fake.calls] == ["u", "u2"]
    with pytest.raises(ProviderError, match="no response for LLMPatient"):
        await fake.generate(system="s", user="u3", schema=LLMPatient)


# ---------- Gemini adapter with a stub client (no network) ----------


class StubGeminiModels:
    def __init__(self, response: Any = None, error: Exception | None = None) -> None:
        self.response, self.error = response, error
        self.calls: list[dict[str, Any]] = []

    async def generate_content(self, *, model: str, contents: str, config: Any) -> Any:
        self.calls.append({"model": model, "contents": contents, "config": config})
        if self.error:
            raise self.error
        return self.response


def gemini_with(models: StubGeminiModels) -> GeminiProvider:
    client = SimpleNamespace(aio=SimpleNamespace(models=models))
    return GeminiProvider("gemini-3.8-flash", no_keys(), client=client)


async def test_gemini_parses_json_and_prices_thinking_tokens_as_output() -> None:
    usage = SimpleNamespace(
        prompt_token_count=2000, candidates_token_count=600, thoughts_token_count=150
    )
    models = StubGeminiModels(SimpleNamespace(text=FACTS_JSON, usage_metadata=usage))
    result = await gemini_with(models).generate(system="SYS", user="TEXT", schema=LLMExtractedFacts)
    assert result.parsed.final_diagnosis.name == "Pulmonary embolism"
    assert (result.input_tokens, result.output_tokens) == (2000, 750)
    assert result.cost_usd == cost_usd("gemini", "gemini-3.8-flash", 2000, 750)
    config = models.calls[0]["config"]
    assert config.system_instruction == "SYS"
    assert config.response_mime_type == "application/json"
    assert config.response_json_schema == LLMExtractedFacts.model_json_schema()
    assert config.thinking_config.thinking_level.value == "LOW"
    assert config.temperature is None


def test_gemini_client_uses_vertex_ai_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def record(**kwargs: Any) -> str:
        seen.update(kwargs)
        return "client"

    monkeypatch.setattr(gemini_module.genai, "Client", record)
    settings = no_keys().model_copy(update={"gcp_project": "demo-project"})
    assert make_gemini_client(settings) == "client"
    assert seen["vertexai"] is True and "enterprise" not in seen
    assert (seen["project"], seen["location"]) == ("demo-project", "global")


def test_gemini_real_client_is_vertex_without_network() -> None:
    settings = no_keys().model_copy(update={"gcp_project": "demo-project"})
    client = make_gemini_client(settings)
    assert client.vertexai is True


async def test_gemini_invalid_json_is_repairable_and_keeps_usage() -> None:
    usage = SimpleNamespace(
        prompt_token_count=100, candidates_token_count=10, thoughts_token_count=None
    )
    models = StubGeminiModels(SimpleNamespace(text='{"patient": {}}', usage_metadata=usage))
    with pytest.raises(InvalidOutput) as excinfo:
        await gemini_with(models).generate(system="s", user="u", schema=LLMExtractedFacts)
    assert "patient.age_years: Field required" in excinfo.value.errors
    assert excinfo.value.usage.input_tokens == 100


async def test_gemini_quota_error_is_retryable_unavailable() -> None:
    quota = genai_errors.ClientError(
        429,
        {"error": {"code": 429, "message": "Resource exhausted", "status": "RESOURCE_EXHAUSTED"}},
    )
    with pytest.raises(ProviderUnavailable) as excinfo:
        await gemini_with(StubGeminiModels(error=quota)).generate(
            system="s", user="u", schema=LLMPatient
        )
    assert excinfo.value.retryable and excinfo.value.status == 429


# ---------- Claude adapter with a stub client (no network) ----------


class StubClaudeMessages:
    def __init__(self, response: Any = None, error: Exception | None = None) -> None:
        self.response, self.error = response, error
        self.calls: list[dict[str, Any]] = []

    async def parse(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


def claude_with(messages: StubClaudeMessages, model: str = "claude-sonnet-5") -> ClaudeProvider:
    return ClaudeProvider(model, no_keys(), client=SimpleNamespace(messages=messages))


def claude_message(parsed: Any, stop_reason: str = "end_turn") -> SimpleNamespace:
    return SimpleNamespace(
        stop_reason=stop_reason,
        parsed_output=parsed,
        usage=SimpleNamespace(input_tokens=3000, output_tokens=900),
    )


@pytest.mark.parametrize("model", ["claude-sonnet-5", "claude-opus-4-8", "claude-opus-5-5"])
async def test_claude_uses_parse_with_low_effort_and_no_sampling_params(model: str) -> None:
    parsed = LLMExtractedFacts.model_validate_json(FACTS_JSON)
    messages = StubClaudeMessages(claude_message(parsed))
    result = await claude_with(messages, model).generate(
        system="SYS", user="TEXT", schema=LLMExtractedFacts
    )
    assert result.parsed == parsed and result.model == model
    assert result.cost_usd == cost_usd("claude", model, 3000, 900)
    call = messages.calls[0]
    assert call["model"] == model
    assert call["output_format"] is LLMExtractedFacts and call["system"] == "SYS"
    assert call["messages"] == [{"role": "user", "content": "TEXT"}]
    # effort is the only lever on every Claude call (spec §10); no sampling params, no thinking
    assert call["output_config"] == {"effort": "low"}
    for banned in ("temperature", "top_p", "top_k", "thinking"):
        assert banned not in call


def test_claude_client_is_anthropic_vertex_on_the_global_region() -> None:
    from anthropic import AsyncAnthropicVertex

    settings = no_keys().model_copy(update={"gcp_project": "demo-project"})
    client = make_claude_client(settings)
    assert isinstance(client, AsyncAnthropicVertex)
    assert (client.project_id, client.region) == ("demo-project", "global")


async def test_claude_refusal_is_not_repairable() -> None:
    with pytest.raises(ProviderError, match="refusal") as excinfo:
        await claude_with(StubClaudeMessages(claude_message(None, "refusal"))).generate(
            system="s", user="u", schema=LLMPatient
        )
    assert not isinstance(excinfo.value, InvalidOutput)


async def test_claude_sdk_validation_error_becomes_invalid_output() -> None:
    try:
        LLMPatient.model_validate_json("{}")
    except ValidationError as exc:
        error = exc
    with pytest.raises(InvalidOutput, match="schema validation") as excinfo:
        await claude_with(StubClaudeMessages(error=error)).generate(
            system="s", user="u", schema=LLMPatient
        )
    assert "age_years: Field required" in excinfo.value.errors


def test_claude_model_id_per_route() -> None:
    # the four §15 IDs are bare on both routes; a date-pinned Vertex ID uses '@'
    assert api_model_id("claude-opus-4-8", vertex=True) == "claude-opus-4-8"
    assert api_model_id("claude-opus-4-8", vertex=False) == "claude-opus-4-8"
    assert api_model_id("claude-example@20260101", vertex=False) == "claude-example-20260101"


# ---------- factory ----------


def test_factory_without_credentials_is_unavailable() -> None:
    for provider in Provider:
        with pytest.raises(ProviderUnavailable) as excinfo:
            get_provider(provider, None, no_keys())
        assert excinfo.value.retryable is False


@pytest.mark.parametrize(
    ("provider", "model"),
    [
        (Provider.GEMINI, "gemini-2.5-flash"),
        (Provider.GEMINI, "gemini-3.5-flash-lite"),
        (Provider.CLAUDE, "claude-sonnet-5-5"),
        (Provider.CLAUDE, "claude-haiku-4-5@20251001"),
    ],
)
def test_factory_enforces_the_allowlist(provider: Provider, model: str) -> None:
    with pytest.raises(UnknownModel, match="choose one of"):
        get_provider(provider, model, no_keys())


def test_factory_builds_each_of_the_four_models() -> None:
    settings = no_keys().model_copy(update={"gcp_project": "demo-project"})
    built = []
    for price in load_pricing().values():
        adapter = get_provider(Provider(price.provider), price.model, settings)
        built.append((adapter.name, adapter.model))
    assert sorted(built) == [
        ("claude", "claude-opus-4-8"),
        ("claude", "claude-opus-5-5"),
        ("claude", "claude-sonnet-5"),
        ("gemini", "gemini-3.8-flash"),
    ]


def test_factory_builds_vertex_adapters_without_network() -> None:
    settings = no_keys().model_copy(update={"gcp_project": "demo-project"})
    gemini = get_provider(Provider.GEMINI, None, settings)
    claude = get_provider(Provider.CLAUDE, "claude-opus-5-5", settings)
    assert (gemini.name, gemini.model) == ("gemini", "gemini-3.8-flash")
    assert (claude.name, claude.model) == ("claude", "claude-opus-5-5")


def test_factory_fake_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PIPELINE_FAKE_LLM", "1")
    provider = get_provider(Provider.CLAUDE, None, no_keys())
    assert isinstance(provider, FakeProvider)
    assert (provider.name, provider.model) == ("claude", "fake-claude")
