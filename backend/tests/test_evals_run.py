from __future__ import annotations

import json
from pathlib import Path

import pytest

from evals.gold import load_gold
from evals.report import EvalReport
from evals.run import (
    GaveUp,
    ModelSpec,
    append_record,
    cache_file,
    default_specs,
    main,
    read_records,
    run_model,
    with_backoff,
)
from pipeline.providers.base import ProviderUnavailable
from pipeline.providers.fake import FakeProvider

FAKE_FLOOR = 0.90


def dirs(tmp_path: Path) -> list[str]:
    return [
        "--cache-dir",
        str(tmp_path / "cache"),
        "--recordings-dir",
        str(tmp_path / "rec"),
        "--reports-dir",
        str(tmp_path / "reports"),
    ]


def test_fake_run_writes_report_and_resumes(tmp_path: Path) -> None:
    assert main(["--models", "fake/fake-gold", *dirs(tmp_path)]) == 0
    report = EvalReport.model_validate_json((tmp_path / "reports" / "latest.json").read_text())
    row = report.models[0]
    assert (row.provider, row.model, row.cases) == ("fake", "fake-gold", len(load_gold()))
    assert row.schema_valid_rate == 1.0 and row.macro_f1 >= FAKE_FLOOR
    assert row.hallucination_rate > 0  # the fake invents one finding on every third case
    assert (tmp_path / "reports" / "latest.md").read_text().startswith("# Extraction eval")
    cached = tmp_path / "cache" / "fake__fake-gold__v1.jsonl"
    lines = cached.read_text().splitlines()
    assert (tmp_path / "rec" / cached.name).read_text().splitlines() == lines
    assert main(["--models", "fake/fake-gold", *dirs(tmp_path)]) == 0
    assert cached.read_text().splitlines() == lines  # resumed: nothing re-run


def test_report_json_keeps_the_shared_contract(tmp_path: Path) -> None:
    main(["--models", "fake/fake-gold", *dirs(tmp_path)])
    data = json.loads((tmp_path / "reports" / "latest.json").read_text())
    assert set(data) == {
        "generated_at",
        "prompt_version",
        "split",
        "gold_cases",
        "models",
        "per_case",
        "honesty_notes",
    }
    assert data["split"] == "all" and data["gold_cases"] == 8
    assert set(data["models"][0]) == {
        "provider",
        "model",
        "cases",
        "schema_valid_rate",
        "schema_valid_first_try_rate",
        "macro_f1",
        "fields",
        "grounded_ratio",
        "hallucination_rate",
        "negation_errors",
        "latency_ms_p50",
        "latency_ms_p95",
        "cost_usd_per_case",
        "tokens_in_avg",
        "tokens_out_avg",
    }
    assert set(data["models"][0]["fields"]) == {
        "patient_age",
        "patient_sex",
        "chief_complaint",
        "final_diagnosis",
        "findings_precision",
        "findings_recall",
        "findings_f1",
        "measurements_precision",
        "measurements_recall",
        "measurements_f1",
    }
    assert set(data["per_case"][0]) == {
        "case_id",
        "provider",
        "model",
        "findings_f1",
        "measurements_f1",
        "diagnosis_correct",
        "grounded_ratio",
        "latency_ms",
        "cost_usd",
        "notes",
    }


async def test_backoff_grows_then_gives_up_without_writing(tmp_path: Path) -> None:
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    quota = ProviderUnavailable("429", retryable=True, status=429)
    fake = FakeProvider(name="fake", model="m", script=[quota] * 20)
    items = load_gold()[:1]
    path = tmp_path / "c.jsonl"
    with pytest.raises(GaveUp):
        await run_model(ModelSpec("fake", "m"), items, fake, path, sleep=fake_sleep, patience_s=300)
    assert slept == [10, 20, 40, 80, 120]  # next 120 s would exceed 300 s of patience
    assert not path.exists()  # no gap recorded


async def test_backoff_recovers_after_transient_errors() -> None:
    calls = 0

    async def flaky() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise ProviderUnavailable("503", retryable=True, status=503)
        return "ok"

    async def no_sleep(_: float) -> None:
        return None

    assert await with_backoff(flaky, sleep=no_sleep) == "ok" and calls == 3
    with pytest.raises(ProviderUnavailable):  # not retryable -> immediate
        await with_backoff(lambda: _raise_permanent(), sleep=no_sleep)


async def _raise_permanent() -> str:
    raise ProviderUnavailable("403", retryable=False, status=403)


async def test_invalid_output_is_recorded_as_schema_invalid(tmp_path: Path) -> None:
    items = load_gold()[:1]
    fake = FakeProvider(name="fake", model="m", script=["{}", "{}", "{}"])
    records = await run_model(ModelSpec("fake", "m"), items, fake, tmp_path / "c.jsonl")
    assert records[0].ok is False and records[0].attempts == 3
    assert "Field required" in (records[0].error or "")


def test_torn_last_line_is_ignored(tmp_path: Path) -> None:
    path = tmp_path / "c.jsonl"
    path.write_text('{"case_id": "torn", "provi')  # crash in the middle of a write
    assert read_records(path) == {}


def test_offline_mode_scores_recordings_only(tmp_path: Path) -> None:
    main(["--models", "fake/fake-gold", *dirs(tmp_path)])
    (tmp_path / "reports" / "latest.json").unlink()
    assert main(["--offline", *dirs(tmp_path)]) == 0
    report = EvalReport.model_validate_json((tmp_path / "reports" / "latest.json").read_text())
    assert [m.model for m in report.models] == ["fake-gold"]  # fallback: no live recordings


def test_cache_file_name_is_filesystem_safe() -> None:
    path = cache_file(Path("x"), ModelSpec("claude", "claude-opus-4-8"))
    assert path.name == "claude__claude-opus-4-8__v1.jsonl"
    assert cache_file(Path("x"), ModelSpec("gemini", "a/b")).name == "gemini__a_b__v1.jsonl"


def test_default_live_models_are_the_four_of_the_spec() -> None:
    assert [spec.label for spec in default_specs()] == [
        "gemini/gemini-3.8-flash",
        "claude/claude-sonnet-5",
        "claude/claude-opus-4-8",
        "claude/claude-opus-5-5",
    ]


def test_split_option_is_gone() -> None:
    with pytest.raises(SystemExit):
        main(["--split", "test", "--offline"])


def test_append_record_after_torn_line_keeps_the_new_record(tmp_path: Path) -> None:
    main(["--models", "fake/fake-gold", *dirs(tmp_path)])
    source = tmp_path / "cache" / "fake__fake-gold__v1.jsonl"
    first = next(iter(read_records(source).values()))
    path = tmp_path / "torn.jsonl"
    path.write_text('{"case_id": "torn", "provi')
    append_record(path, first)
    assert list(read_records(path)) == [first.case_id]
