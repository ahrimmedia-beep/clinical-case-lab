from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from seeds.ai_players import DEFAULT_MODELS, main, parse_models, run_ai_players

CASES = [
    {"slug": "lam-hero-aaaaaa", "review_status": "approved"},
    {"slug": "pe-bbbbbb", "review_status": "approved"},
    {"slug": "ai-draft-cccccc", "review_status": "draft"},
]


def summary(slug: str, provider: str, model: str) -> dict[str, Any]:
    return {
        "attempt_id": 1,
        "label": f"ai:{model}",
        "provider": provider,
        "model": model,
        "points": 3,
        "max_points": 4,
        "diagnosis_text": "x",
        "diagnosis_correct": True,
        "confidence": 4,
        "calibration": "calibrated",
        "latency_ms": 1200,
        "cost_usd": 0.01,
    }


class Api:
    def __init__(self, statuses: list[int] | None = None) -> None:
        self.statuses = list(statuses or [])
        self.posts: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/api/cases":
            return httpx.Response(200, json=CASES)
        self.posts.append(request)
        status = self.statuses.pop(0) if self.statuses else 201
        if status != 201:
            return httpx.Response(status, json={"title": "nope", "status": status})
        slug = request.url.path.split("/")[3]
        body = json.loads(request.content)
        return httpx.Response(201, json=summary(slug, body["provider"], body["model"]))

    def client(self) -> httpx.Client:
        return httpx.Client(
            base_url="https://api.example.test",
            headers={"X-Internal-Key": "k"},
            transport=httpx.MockTransport(self),
        )


def test_default_models_are_the_four_of_the_spec() -> None:
    assert [f"{p}/{m}" for p, m in DEFAULT_MODELS] == [
        "gemini/gemini-3.8-flash",
        "claude/claude-sonnet-5",
        "claude/claude-opus-4-8",
        "claude/claude-opus-5-5",
    ]


def test_every_approved_case_times_every_model() -> None:
    api = Api()
    results = run_ai_players(api.client(), None, DEFAULT_MODELS, sleep=lambda _: None)
    assert len(api.posts) == 2 * 4 and all(r.ok for r in results)
    paths = {r.url.path for r in api.posts}
    assert paths == {"/api/cases/lam-hero-aaaaaa/ai-attempts", "/api/cases/pe-bbbbbb/ai-attempts"}
    assert all(r.headers["x-internal-key"] == "k" for r in api.posts)
    bodies = [json.loads(r.content) for r in api.posts[:4]]
    assert bodies == [{"provider": p, "model": m} for p, m in DEFAULT_MODELS]


def test_slugs_and_models_can_be_chosen() -> None:
    api = Api()
    models = parse_models("claude/claude-opus-4-8")
    results = run_ai_players(api.client(), ["pe-bbbbbb"], models, sleep=lambda _: None)
    assert [(r.slug, r.label) for r in results] == [("pe-bbbbbb", "claude/claude-opus-4-8")]


def test_unavailable_is_retried_and_a_failure_does_not_stop_the_run() -> None:
    api = Api(statuses=[503, 201, 502])
    waits: list[float] = []
    models = parse_models("gemini/gemini-3.8-flash,claude/claude-opus-5-5")
    results = run_ai_players(api.client(), ["pe-bbbbbb"], models, sleep=waits.append)
    assert [r.status for r in results] == [201, 502]
    assert waits == [20.0] and len(api.posts) == 3


def test_bad_model_spec_is_rejected() -> None:
    with pytest.raises(SystemExit):
        parse_models("gpt-4")
    with pytest.raises(SystemExit):
        parse_models("claude/claude-sonnet-5-5")  # not in pricing.yaml


def test_main_exit_code_reflects_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    api = Api(statuses=[201, 502])
    monkeypatch.setattr("seeds.ai_players.api_client", lambda base, key: api.client())
    monkeypatch.setattr("seeds.ai_players.sleep", lambda _: None)
    args = ["--api", "https://api.example.test", "--slugs", "pe-bbbbbb"]
    assert main([*args, "--models", "gemini/gemini-3.8-flash,claude/claude-sonnet-5"]) == 1
    api.statuses = [201]
    assert main([*args, "--models", "gemini/gemini-3.8-flash"]) == 0
