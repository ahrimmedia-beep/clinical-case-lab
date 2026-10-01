"""Command line.

python -m pipeline.cli extract FILE --provider gemini|claude [--model M] [--author-model M]
    Prints the ExtractResponse JSON. Live providers need GCP_PROJECT + ADC (or an API key);
    PIPELINE_FAKE_LLM=1 runs the deterministic fake provider instead.
python -m pipeline.cli prewarm --api URL [--samples FILE] [--providers gemini claude]
    Posts the /studio samples to a deployed API once, so the live demo answers from the cache.
    The internal key comes from --key or INTERNAL_API_KEY.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections.abc import Sequence
from pathlib import Path

import structlog

from app.config import get_settings
from app.schemas.extract import Provider
from pipeline.factory import UnknownModel, get_provider
from pipeline.phi import PhiLeakError
from pipeline.prewarm import DEFAULT_SAMPLES, load_samples, prewarm
from pipeline.providers.base import ProviderError
from pipeline.run import run_pipeline


def _logs_to_stderr() -> None:
    """Keep stdout for the JSON result; the factory runs per call, so it follows sys.stderr."""
    structlog.configure(logger_factory=lambda *_: structlog.PrintLogger(file=sys.stderr))


def main(argv: Sequence[str] | None = None) -> int:
    _logs_to_stderr()
    parser = argparse.ArgumentParser(prog="python -m pipeline.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    extract = commands.add_parser("extract", help="clinical text file -> ExtractResponse JSON")
    extract.add_argument("file", type=Path)
    extract.add_argument("--provider", choices=[p.value for p in Provider], default="gemini")
    extract.add_argument("--model", default=None, help="default: the provider's default model")
    extract.add_argument("--author-model", default=None, help="model for the authoring step")
    warm = commands.add_parser("prewarm", help="post the /studio samples to a deployed API")
    warm.add_argument("--api", required=True, help="API base URL, e.g. https://api-...run.app")
    warm.add_argument("--samples", type=Path, default=DEFAULT_SAMPLES)
    warm.add_argument(
        "--providers", nargs="+", choices=[p.value for p in Provider], default=["gemini", "claude"]
    )
    warm.add_argument("--key", default=None, help="X-Internal-Key (default: INTERNAL_API_KEY)")
    args = parser.parse_args(argv)
    if args.command == "prewarm":
        return _prewarm(args)

    text = args.file.read_text(encoding="utf-8")
    settings = get_settings()
    provider_kind = Provider(args.provider)
    try:
        provider = get_provider(provider_kind, args.model, settings)
        author = (
            get_provider(provider_kind, args.author_model, settings) if args.author_model else None
        )
        response = asyncio.run(run_pipeline(text, provider, author))
    except (ProviderError, UnknownModel, PhiLeakError) as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(response.model_dump_json(indent=2))
    return 0


def _prewarm(args: argparse.Namespace) -> int:
    try:
        texts = load_samples(args.samples)
    except (OSError, ValueError, KeyError) as exc:
        print(f"error: cannot read samples from {args.samples}: {exc}", file=sys.stderr)
        return 2
    key = args.key or os.environ.get("INTERNAL_API_KEY") or None
    results = prewarm(args.api, texts, providers=args.providers, key=key)
    for i, result in enumerate(results):
        print(
            f"sample {i // len(args.providers) + 1} {result.provider}: {result.status} "
            f"({result.latency_ms} ms)",
            file=sys.stderr,
        )
    return 0 if all(r.status == 200 for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
