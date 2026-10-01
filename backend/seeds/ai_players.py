"""Let AI models play the showcase cases (★1): one blinded attempt per case x model.

Each call is `POST /api/cases/{slug}/ai-attempts`: the API plays the case server-side (Cloud Run
has Vertex AI access), scores it like a physician's attempt and stores it as `ai:<model>`. The
latest attempt per model shows up as a labelled marker on the percentile curve. Re-running is
harmless: only the latest attempt per model is shown.

Usage (from backend/, after `seeds.load`):
    uv run python -m seeds.ai_players --api https://api-...run.app [--models p/m,...] [--slugs ...]
Defaults: every physician-reviewed (approved) case x the four models in pipeline/pricing.yaml.
The `X-Internal-Key` header comes from `--key` (default `$INTERNAL_API_KEY`).
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from time import sleep
from typing import Any

import httpx

from pipeline.pricing import allowed_models, load_pricing

DEFAULT_MODELS: list[tuple[str, str]] = [(p.provider, p.model) for p in load_pricing().values()]
RETRYABLE = {429, 503, 504}  # 502 = the model's answer was unusable: not retried (costs money)
ATTEMPTS = 3
FIRST_DELAY_S = 20.0
TIMEOUT_S = 300.0  # two model calls; Opus can take a minute


@dataclass(frozen=True)
class Result:
    slug: str
    label: str  # provider/model
    status: int
    body: dict[str, Any]

    @property
    def ok(self) -> bool:
        return self.status == 201


def parse_models(value: str) -> list[tuple[str, str]]:
    specs: list[tuple[str, str]] = []
    for part in filter(None, (p.strip() for p in value.split(","))):
        provider, _, model = part.partition("/")
        if provider not in ("gemini", "claude") or model not in allowed_models(provider):
            raise SystemExit(f"unknown model {part!r}; use provider/model from pricing.yaml")
        specs.append((provider, model))
    return specs


def api_client(base_url: str, key: str | None) -> httpx.Client:
    headers = {"X-Internal-Key": key} if key else {}
    return httpx.Client(base_url=base_url.rstrip("/"), headers=headers, timeout=TIMEOUT_S)


def approved_slugs(client: httpx.Client) -> list[str]:
    response = client.get("/api/cases")
    response.raise_for_status()
    return [c["slug"] for c in response.json() if c.get("review_status") == "approved"]


def run_ai_players(
    client: httpx.Client,
    slugs: Sequence[str] | None,
    models: Sequence[tuple[str, str]],
    *,
    sleep: Callable[[float], None] = sleep,
) -> list[Result]:
    results: list[Result] = []
    for slug in slugs or approved_slugs(client):
        for provider, model in models:
            delay = FIRST_DELAY_S
            for attempt in range(1, ATTEMPTS + 1):
                response = client.post(
                    f"/api/cases/{slug}/ai-attempts", json={"provider": provider, "model": model}
                )
                if response.status_code not in RETRYABLE or attempt == ATTEMPTS:
                    break
                sleep(delay)
                delay *= 2
            try:
                body: dict[str, Any] = response.json()
            except ValueError:
                body = {"detail": response.text[:300]}
            results.append(Result(slug, f"{provider}/{model}", response.status_code, body))
    return results


def _line(result: Result) -> str:
    if not result.ok:
        detail = result.body.get("detail") or result.body.get("title") or ""
        return f"FAIL {result.status} {result.slug} {result.label}: {detail}"
    b = result.body
    verdict = "right" if b["diagnosis_correct"] else "wrong"
    return (
        f"ok   {result.slug} {result.label}: {b['points']}/{b['max_points']} pts, "
        f"diagnosis {verdict} ({b['diagnosis_text']!r}, confidence {b['confidence']}, "
        f"{b['calibration']}), {b['latency_ms'] / 1000:.1f} s, ${b['cost_usd']:.4f}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Let AI models play the showcase cases.")
    parser.add_argument("--api", default=os.environ.get("API_BASE_URL", "http://localhost:8000"))
    parser.add_argument("--key", default=os.environ.get("INTERNAL_API_KEY"))
    parser.add_argument("--models", default="", help="comma-separated provider/model list")
    parser.add_argument("--slugs", default="", help="comma-separated slugs (default: approved)")
    args = parser.parse_args(argv)
    models = parse_models(args.models) or DEFAULT_MODELS
    slugs = [s.strip() for s in args.slugs.split(",") if s.strip()] or None
    with api_client(args.api, args.key) as client:
        results = run_ai_players(client, slugs, models, sleep=sleep)
    for result in results:
        print(_line(result))
    return 0 if results and all(r.ok for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
