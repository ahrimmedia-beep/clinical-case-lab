from __future__ import annotations

import json
from pathlib import Path

import pytest
import structlog

from pipeline.cli import main as cli_main
from pipeline.phi import PhiLeakError
from pipeline.providers.fake import SAMPLE_TEXT_FILE, FakeProvider
from pipeline.run import run_pipeline

SAMPLE = SAMPLE_TEXT_FILE.read_text()


@pytest.fixture(autouse=True)
def no_local_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty variable beats a value in a developer's local .env file: never call Vertex."""
    for key in ("GCP_PROJECT", "GEMINI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.setenv(key, "")


async def test_run_pipeline_end_to_end_with_the_fake_provider() -> None:
    fake = FakeProvider.default(name="gemini", model="fake-model")
    with structlog.testing.capture_logs() as logs:
        response = await run_pipeline(SAMPLE, fake)
    assert "Whitfield" not in response.source_text and "[NAME_1]" in response.source_text
    assert {p.label: p.count for p in response.phi} == {"NAME": 2, "DATE": 1, "PHONE": 1, "ID": 1}
    assert all("Whitfield" not in call.user for call in fake.calls)
    assert response.grounded_ratio == 1.0 and response.warnings == []
    for span in response.spans:
        assert response.source_text[span.start : span.end] == span.quote
    assert [s.path for s in response.spans][:2] == ["findings[0]", "findings[1]"]
    assert response.case.source is not None and response.case.source.kind == "llm"
    assert response.case.source.text == response.source_text  # de-identified text, for review
    assert response.provider == "gemini" and response.prompt_version == "v1"
    assert response.usage.input_tokens == 2 * 1200 and response.usage.output_tokens == 2 * 400

    event = next(e for e in logs if e["event"] == "pipeline_completed")
    for key in (
        "provider",
        "model",
        "input_tokens",
        "output_tokens",
        "cost_usd",
        "latency_ms",
        "grounded_ratio",
    ):
        assert key in event
    assert not any(isinstance(v, str) and "shortness of breath" in v for v in event.values())


async def test_separate_author_model_is_recorded() -> None:
    extractor = FakeProvider.default(name="claude", model="claude-sonnet-5")
    author = FakeProvider.default(name="claude", model="claude-opus-4-8")
    response = await run_pipeline(SAMPLE, extractor, author)
    assert response.case.source is not None
    assert response.case.source.model == "claude-sonnet-5 / claude-opus-4-8"
    assert len(extractor.calls) == 1 and len(author.calls) == 1


async def test_overlong_masked_text_is_not_stored_on_the_case(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("pipeline.run.SOURCE_TEXT_LIMIT", 100)
    response = await run_pipeline(SAMPLE, FakeProvider.default())
    assert response.case.source is not None and response.case.source.text is None
    assert any("source text not stored" in w for w in response.warnings)
    assert len(response.source_text) > 100  # the studio still gets the full masked text


async def test_phi_guard_stops_before_any_model_call(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("pipeline.run.deidentify", lambda text: (text, []))  # simulate a bug
    fake = FakeProvider.default()
    with pytest.raises(PhiLeakError):
        await run_pipeline(SAMPLE, fake)
    assert fake.calls == []


def test_cli_prints_extract_response(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    monkeypatch.setenv("PIPELINE_FAKE_LLM", "1")
    note = tmp_path / "note.txt"
    note.write_text(SAMPLE)
    assert cli_main(["extract", str(note), "--provider", "claude"]) == 0
    body = json.loads(capsys.readouterr().out)
    assert body["provider"] == "claude" and body["model"] == "fake-claude"
    assert body["case"]["title"] == "Sudden breathlessness after a long flight"


def test_cli_reports_missing_credentials(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    note = tmp_path / "note.txt"
    note.write_text(SAMPLE)
    assert cli_main(["extract", str(note), "--provider", "gemini"]) == 2
    assert "ProviderUnavailable" in capsys.readouterr().err
