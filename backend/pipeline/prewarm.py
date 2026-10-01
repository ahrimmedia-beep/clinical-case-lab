"""Pre-warm the /api/extract cache with the /studio samples after a deploy.

The samples live in the web app (`web/src/data/studio-samples.ts`); reading that file keeps one
source of truth, so the cache keys match what the studio sends byte for byte. A JSON list of
strings or `{"text": ...}` objects works too.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

DEFAULT_SAMPLES = Path(__file__).resolve().parents[2] / "web" / "src" / "data" / "studio-samples.ts"
RATE_LIMIT_WAIT_S = 61.0  # the per-IP window is one minute
MAX_TRIES = 3
TIMEOUT_S = 300.0  # a cold extraction (two model calls) can take a minute or more

# `text: "..."` or `text:\n  "..."` with a JSON-compatible double-quoted string literal.
_TS_TEXT = re.compile(r'\btext:\s*("(?:[^"\\\n]|\\.)*")')


@dataclass(frozen=True)
class PrewarmResult:
    provider: str
    status: int
    latency_ms: int | None


def load_samples(path: Path) -> list[str]:
    raw = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        items: list[Any] = json.loads(raw)
        return [item if isinstance(item, str) else str(item["text"]) for item in items]
    return [json.loads(literal) for literal in _TS_TEXT.findall(raw)]


def prewarm(
    api: str,
    texts: Sequence[str],
    *,
    providers: Sequence[str],
    key: str | None,
    transport: httpx.BaseTransport | None = None,
    sleep: Callable[[float], None] | None = None,
) -> list[PrewarmResult]:
    """POST every text once per provider; wait out a 429 and retry (up to MAX_TRIES)."""
    pause = sleep or time.sleep
    headers = {"X-Internal-Key": key} if key else {}
    results: list[PrewarmResult] = []
    with httpx.Client(
        base_url=api.rstrip("/"), headers=headers, timeout=TIMEOUT_S, transport=transport
    ) as client:
        for text in texts:
            for provider in providers:
                for attempt in range(1, MAX_TRIES + 1):
                    response = client.post(
                        "/api/extract", json={"text": text, "provider": provider}
                    )
                    if response.status_code != 429 or attempt == MAX_TRIES:
                        break
                    pause(RATE_LIMIT_WAIT_S)
                latency = None
                if response.status_code == 200:
                    latency = int(response.json().get("usage", {}).get("latency_ms", 0))
                results.append(PrewarmResult(provider, response.status_code, latency))
    return results
