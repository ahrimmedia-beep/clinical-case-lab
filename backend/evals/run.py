"""Eval runner: python -m evals.run [--models gemini/gemini-3.8-flash,claude/claude-sonnet-5]

Without --models a live run covers the four models in pipeline/pricing.yaml (spec §15) on all
eight gold cases (there is no dev/test split).

Live mode calls each model on each gold case (extraction step only) and appends every result to
evals/.cache/<provider>__<model>__<prompt_version>.jsonl immediately (flush + fsync). A rerun
skips cases already in the cache, so a crash or Ctrl-C loses at most one case. 429/5xx/network
errors back off 10 s -> 120 s for up to ~30 min, then the run stops with exit code 3 and writes
nothing for that case. Finished model files are copied to evals/recordings/ (committed).

--offline recomputes the report from evals/recordings/ only (CI, no keys, no network).
Live runs need GCP_PROJECT + ADC (`gcloud auth application-default login`); otherwise use
--offline.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import sys
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from pathlib import Path

import structlog

from app.config import get_settings
from app.schemas.extract import Provider
from evals.fake_gold import fake_gold_provider
from evals.gold import GoldItem, load_gold
from evals.report import Record, build_report, sha256, write_report
from pipeline.extract import ExtractionFailed, extract_facts
from pipeline.factory import get_provider
from pipeline.phi import deidentify
from pipeline.pricing import load_pricing
from pipeline.prompts import PROMPT_VERSION
from pipeline.providers.base import LLMProvider, ProviderError, ProviderUnavailable

EVALS_DIR = Path(__file__).parent
log = structlog.get_logger()

type Sleep = Callable[[float], Awaitable[None]]


class GaveUp(Exception):
    """The provider stayed unavailable longer than the patience budget."""


@dataclass(frozen=True)
class ModelSpec:
    provider: str
    model: str

    @property
    def label(self) -> str:
        return f"{self.provider}/{self.model}"


def parse_models(value: str) -> list[ModelSpec]:
    specs: list[ModelSpec] = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        provider, _, model = part.partition("/")
        if provider not in {"gemini", "claude", "fake"} or not model:
            raise SystemExit(
                f"bad model spec {part!r}: use provider/model, e.g. gemini/gemini-3.8-flash"
            )
        specs.append(ModelSpec(provider, model))
    return specs


def default_specs() -> list[ModelSpec]:
    """The live default: every model in pricing.yaml, in file order."""
    return [ModelSpec(p.provider, p.model) for p in load_pricing().values()]


def cache_file(directory: Path, spec: ModelSpec, prompt_version: str = PROMPT_VERSION) -> Path:
    safe_model = spec.model.replace("/", "_")
    return directory / f"{spec.provider}__{safe_model}__{prompt_version}.jsonl"


def read_records(path: Path) -> dict[str, Record]:
    """Records by case id; a torn last line (crash mid-write) is ignored and re-run."""
    records: dict[str, Record] = {}
    if not path.exists():
        return records
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = Record.model_validate_json(line)
        except ValueError:
            log.warning("eval_cache_bad_line", file=path.name)
            continue
        records[record.case_id] = record
    return records


def append_record(path: Path, record: Record) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    needs_newline = (
        path.exists() and path.stat().st_size > 0 and not path.read_bytes().endswith(b"\n")
    )
    with path.open("a", encoding="utf-8") as fh:
        if needs_newline:
            fh.write("\n")  # isolate a torn line left by a crash
        fh.write(record.model_dump_json() + "\n")
        fh.flush()
        os.fsync(fh.fileno())


async def with_backoff[T](
    call: Callable[[], Awaitable[T]],
    *,
    sleep: Sleep = asyncio.sleep,
    first_delay_s: float = 10.0,
    max_delay_s: float = 120.0,
    patience_s: float = 1800.0,
) -> T:
    delay, waited = first_delay_s, 0.0
    while True:
        try:
            return await call()
        except ProviderUnavailable as exc:
            if not exc.retryable:
                raise
            if waited + delay > patience_s:
                raise GaveUp(f"provider unavailable for {waited:.0f} s: {exc}") from exc
            log.warning("eval_backoff", delay_s=delay, status=exc.status)
            await sleep(delay)
            waited += delay
            delay = min(delay * 2, max_delay_s)


async def run_model(
    spec: ModelSpec,
    items: Sequence[GoldItem],
    provider: LLMProvider,
    cache_path: Path,
    *,
    sleep: Sleep = asyncio.sleep,
    patience_s: float = 1800.0,
) -> list[Record]:
    done = read_records(cache_path)
    for item in items:
        if item.case_id in done:
            continue
        masked, _ = deidentify(item.text)
        started = datetime.now(UTC)
        base = {
            "case_id": item.case_id,
            "provider": spec.provider,
            "model": spec.model,
            "prompt_version": PROMPT_VERSION,
            "text_sha256": sha256(masked),
            "recorded_at": started.isoformat(timespec="seconds"),
        }
        try:
            outcome = await with_backoff(
                partial(extract_facts, masked, provider), sleep=sleep, patience_s=patience_s
            )
            record = Record(
                **base,
                ok=True,
                attempts=outcome.attempts,
                facts=outcome.facts,
                error=None,
                latency_ms=outcome.usage.latency_ms,
                input_tokens=outcome.usage.input_tokens,
                output_tokens=outcome.usage.output_tokens,
                cost_usd=outcome.usage.cost_usd,
            )
        except ExtractionFailed as exc:
            record = Record(
                **base,
                ok=False,
                attempts=exc.attempts,
                facts=None,
                error=exc.last_errors[:500],
                latency_ms=exc.usage.latency_ms,
                input_tokens=exc.usage.input_tokens,
                output_tokens=exc.usage.output_tokens,
                cost_usd=exc.usage.cost_usd,
            )
        except ProviderUnavailable:
            raise
        except ProviderError as exc:  # e.g. refusal: a real, recordable failure for this case
            record = Record(
                **base,
                ok=False,
                attempts=1,
                facts=None,
                error=str(exc)[:500],
                latency_ms=0,
                input_tokens=0,
                output_tokens=0,
                cost_usd=0.0,
            )
        append_record(cache_path, record)
        done[item.case_id] = record
        log.info("eval_case_done", model=spec.label, case=item.case_id, ok=record.ok)
    return [done[item.case_id] for item in items if item.case_id in done]


def build_provider(spec: ModelSpec, items: Sequence[GoldItem]) -> LLMProvider:
    if spec.provider == "fake":
        return fake_gold_provider(items)
    return get_provider(Provider(spec.provider), spec.model, get_settings())


def _offline_specs(recordings: Path, include_fake: bool) -> list[ModelSpec]:
    specs = []
    for path in sorted(recordings.glob(f"*__{PROMPT_VERSION}.jsonl")):
        provider, model, _ = path.name.removesuffix(".jsonl").split("__")
        specs.append(ModelSpec(provider, model))
    real = [s for s in specs if s.provider != "fake"]
    if real and not include_fake:
        return real
    return specs


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m evals.run")
    parser.add_argument("--models", default="", help="comma-separated provider/model list")
    parser.add_argument("--offline", action="store_true", help="score evals/recordings only")
    parser.add_argument("--include-fake", action="store_true", help="offline: keep fake rows")
    parser.add_argument("--no-record", action="store_true", help="do not copy to recordings/")
    parser.add_argument("--cache-dir", type=Path, default=EVALS_DIR / ".cache")
    parser.add_argument("--recordings-dir", type=Path, default=EVALS_DIR / "recordings")
    parser.add_argument("--reports-dir", type=Path, default=EVALS_DIR / "reports")
    args = parser.parse_args(argv)

    items = load_gold()
    records_by_model: dict[tuple[str, str], list[Record]] = {}

    if args.offline:
        specs = parse_models(args.models) or _offline_specs(args.recordings_dir, args.include_fake)
        wanted = {item.case_id for item in items}
        for spec in specs:
            recorded = read_records(cache_file(args.recordings_dir, spec))
            chosen = [r for r in recorded.values() if r.case_id in wanted]
            if chosen:
                records_by_model[(spec.provider, spec.model)] = chosen
    else:
        specs = parse_models(args.models) or default_specs()
        for spec in specs:
            path = cache_file(args.cache_dir, spec)
            try:
                provider = build_provider(spec, items)
                records = asyncio.run(run_model(spec, items, provider, path))
            except GaveUp as exc:
                print(
                    f"error: {spec.label}: {exc}. Progress is cached; rerun to resume.",
                    file=sys.stderr,
                )
                return 3
            except ProviderError as exc:
                print(f"error: {spec.label}: {type(exc).__name__}: {exc}", file=sys.stderr)
                return 2
            records_by_model[(spec.provider, spec.model)] = records
            if not args.no_record:
                args.recordings_dir.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, args.recordings_dir / path.name)

    report = build_report(records_by_model, items, prompt_version=PROMPT_VERSION)
    write_report(report, args.reports_dir)
    for row in report.models:
        print(
            f"{row.provider}/{row.model}: macro-F1 {row.macro_f1:.3f} "
            f"(valid {row.schema_valid_rate:.0%}, grounded {row.grounded_ratio:.0%})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
