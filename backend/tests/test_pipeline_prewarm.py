from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from pipeline.cli import main as cli_main
from pipeline.prewarm import DEFAULT_SAMPLES, load_samples, prewarm

TS_SAMPLES = """export type StudioSample = { id: string; label: string; text: string };

/** Synthetic notes. */
export const STUDIO_SAMPLES: StudioSample[] = [
  {
    id: "pe",
    label: "Breathless after a flight",
    text:
      "ED note. A 34-year-old woman with \\"sudden\\" breathlessness on inspiration.",
  },
  {
    id: "ptx",
    label: "Sudden pain at a desk",
    text: "Clinic letter. A 22-year-old man with sudden left-sided chest pain at his desk.",
  },
];
"""


def test_load_samples_reads_the_web_typescript_file(tmp_path: Path) -> None:
    path = tmp_path / "studio-samples.ts"
    path.write_text(TS_SAMPLES)
    assert load_samples(path) == [
        'ED note. A 34-year-old woman with "sudden" breathlessness on inspiration.',
        "Clinic letter. A 22-year-old man with sudden left-sided chest pain at his desk.",
    ]


def test_load_samples_reads_json(tmp_path: Path) -> None:
    path = tmp_path / "samples.json"
    path.write_text(json.dumps([{"id": "a", "text": "first note"}, "second note"]))
    assert load_samples(path) == ["first note", "second note"]


def test_default_samples_are_the_web_studio_file() -> None:
    assert DEFAULT_SAMPLES.parts[-4:] == ("web", "src", "data", "studio-samples.ts")


def recorder(statuses: list[int]) -> tuple[list[httpx.Request], httpx.MockTransport]:
    seen: list[httpx.Request] = []
    queue = list(statuses)

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        status = queue.pop(0) if queue else 200
        return httpx.Response(status, json={"usage": {"latency_ms": 1}, "title": "x"})

    return seen, httpx.MockTransport(handle)


def test_prewarm_posts_every_sample_per_provider_with_the_key() -> None:
    seen, transport = recorder([])
    results = prewarm(
        "https://api.example.test/",
        ["note one", "note two"],
        providers=["gemini", "claude"],
        key="secret",
        transport=transport,
        sleep=lambda _: None,
    )
    assert [r.status for r in results] == [200] * 4
    assert all(str(r.url) == "https://api.example.test/api/extract" for r in seen)
    assert all(r.headers["x-internal-key"] == "secret" for r in seen)
    bodies: list[dict[str, Any]] = [json.loads(r.content) for r in seen]
    assert [(b["text"], b["provider"]) for b in bodies] == [
        ("note one", "gemini"),
        ("note one", "claude"),
        ("note two", "gemini"),
        ("note two", "claude"),
    ]


def test_prewarm_waits_out_the_rate_limit_and_retries() -> None:
    seen, transport = recorder([200, 429, 200])
    waits: list[float] = []
    results = prewarm(
        "https://api.example.test",
        ["note one", "note two"],
        providers=["gemini"],
        key=None,
        transport=transport,
        sleep=waits.append,
    )
    assert [r.status for r in results] == [200, 200]
    assert len(seen) == 3 and waits == [61.0]
    assert "x-internal-key" not in seen[0].headers


def test_cli_prewarm_exit_codes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    samples = tmp_path / "samples.json"
    samples.write_text(json.dumps(["only note"]))
    calls: list[dict[str, Any]] = []

    def fake_prewarm(api: str, texts: list[str], **kwargs: Any) -> list[Any]:
        calls.append({"api": api, "texts": texts, **kwargs})
        return []

    monkeypatch.setattr("pipeline.cli.prewarm", fake_prewarm)
    monkeypatch.setenv("INTERNAL_API_KEY", "from-env")
    args = ["prewarm", "--api", "https://api.example.test", "--samples", str(samples)]
    assert cli_main(args) == 0
    assert calls[0]["texts"] == ["only note"] and calls[0]["key"] == "from-env"
    assert calls[0]["providers"] == ["gemini", "claude"]
    assert cli_main(["prewarm", "--api", "x", "--samples", str(tmp_path / "missing.ts")]) == 2
