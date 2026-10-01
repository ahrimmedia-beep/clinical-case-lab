"""POST /api/cases/{slug}/ai-attempts with the fake provider and stand-ins for the repository.

The DB layer is track A's (tested in tests/db); here the stand-in `record_attempt` uses the real
pure scoring, so the summary is exactly what the stored attempt would score.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
import structlog
from fastapi.testclient import TestClient

from app.config import get_settings
from app.db.engine import get_engine
from app.main import create_app
from app.repository.attempts import RecordedAttempt
from app.repository.cases import StoredCase
from app.schemas.attempt import AttemptIn
from app.schemas.case import ClinicalCase, ReviewStatus
from app.scoring import score_attempt
from pipeline.models import LLMPlayerTurn1, LLMPlayerTurn2
from pipeline.providers.base import ProviderError, ProviderUnavailable
from pipeline.providers.fake import FakeProvider

SLUG = "breathless-after-a-flight-1a2b3c"
KEY = {"X-Internal-Key": "test-key"}

# Fixed, provider-neutral strings (pipeline/providers/base.py); the raw SDK text never reaches
# the client and is asserted to land only in the server log.
NOT_AVAILABLE = "This model is not available on the server right now. Switch to the other model."
BUSY = (
    "The model provider is rate-limiting requests right now. "
    "Try again in a minute, or switch to the other model."
)
UNUSABLE = (
    "The model's answer could not be turned into a valid case. "
    "Try again, or switch to the other model."
)


class FakeEngine:
    def __init__(self) -> None:
        self.connections = 0

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[object]:
        self.connections += 1
        yield object()


@pytest.fixture
def stored(case_pe: dict[str, Any]) -> StoredCase:
    case = ClinicalCase.model_validate(case_pe)
    return StoredCase(
        id=11, slug=SLUG, case=case, review_status=ReviewStatus.APPROVED, reviewed_at=None
    )


@pytest.fixture
def recorded() -> list[dict[str, Any]]:
    return []


@pytest.fixture
def client(
    monkeypatch: pytest.MonkeyPatch, stored: StoredCase, recorded: list[dict[str, Any]]
) -> Iterator[TestClient]:
    for key in ("GCP_PROJECT", "GEMINI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.setenv(key, "")  # an empty variable beats a developer's local .env
    monkeypatch.setenv("INTERNAL_API_KEY", "test-key")
    monkeypatch.setenv("PIPELINE_FAKE_LLM", "1")
    get_settings.cache_clear()

    async def load_stored_case(conn: object, slug: str) -> StoredCase | None:
        return stored if slug == SLUG else None

    async def record_attempt(
        conn: object, case: str, attempt: AttemptIn, *, simulated_label: str | None = None
    ) -> RecordedAttempt:
        recorded.append({"slug": case, "attempt": attempt, "label": simulated_label})
        score = score_attempt(stored.case, attempt)
        return RecordedAttempt(901, stored.id, SLUG, stored.case, score)

    monkeypatch.setattr("app.routers.ai_players.load_stored_case", load_stored_case)
    monkeypatch.setattr("app.routers.ai_players.record_attempt", record_attempt)
    app = create_app()
    engine = FakeEngine()
    app.dependency_overrides[get_engine] = lambda: engine
    app.state.fake_engine = engine
    yield TestClient(app)
    get_settings.cache_clear()


def post(client: TestClient, headers: dict[str, str] | None = None, **body: Any) -> Any:
    payload = {"provider": "claude", **body}
    return client.post(f"/api/cases/{SLUG}/ai-attempts", json=payload, headers=headers or KEY)


def test_ai_attempt_is_scored_stored_and_summarised(
    client: TestClient, recorded: list[dict[str, Any]]
) -> None:
    response = post(client)
    assert response.status_code == 201, response.text
    body = response.json()
    # the default fake player picks A+B everywhere and names pulmonary embolism, confidence 4
    assert body == {
        "attempt_id": 901,
        "label": "ai:fake-claude",
        "provider": "claude",
        "model": "fake-claude",
        "points": 3,
        "max_points": 3,
        "diagnosis_text": "Pulmonary embolism",
        "diagnosis_correct": True,
        "confidence": 4,
        "calibration": "calibrated",
        "latency_ms": 10,
        "cost_usd": 0.0,
    }
    (stored_attempt,) = recorded
    assert stored_attempt["slug"] == SLUG and stored_attempt["label"] == "ai:fake-claude"
    assert stored_attempt["attempt"].choices["treatment"] == ["A", "B"]


def test_db_connections_are_not_held_during_the_model_calls(client: TestClient) -> None:
    assert post(client).status_code == 201
    assert client.app.state.fake_engine.connections == 2  # type: ignore[attr-defined]


def test_label_carries_the_requested_model(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, recorded: list[dict[str, Any]]
) -> None:
    monkeypatch.delenv("PIPELINE_FAKE_LLM")
    player = FakeProvider(
        name="claude",
        model="claude-opus-4-8",
        script=[
            LLMPlayerTurn1(interview=["A"], differential=["A", "B"], workup=["A"]),
            LLMPlayerTurn2(diagnosis="PE or pneumothorax", confidence=5, treatment=["A", "C"]),
        ],
    )
    seen: list[tuple[Any, ...]] = []

    def get_provider(*args: Any) -> FakeProvider:
        seen.append(args)
        return player

    monkeypatch.setattr("app.routers.ai_players.get_provider", get_provider)
    response = post(client, model="claude-opus-4-8")
    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["label"], body["model"]) == ("ai:claude-opus-4-8", "claude-opus-4-8")
    # hedged diagnosis is wrong; the harmful thrombolysis zeroes treatment; confident + wrong
    assert (body["points"], body["diagnosis_correct"]) == (0, False)
    assert body["calibration"] == "overconfident"
    assert recorded[-1]["label"] == "ai:claude-opus-4-8"
    assert seen[0][1] == "claude-opus-4-8"


def test_wrong_or_missing_key_is_401(client: TestClient) -> None:
    assert post(client, headers={"X-Internal-Key": "nope"}).status_code == 401
    response = client.post(f"/api/cases/{SLUG}/ai-attempts", json={"provider": "claude"})
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")


def test_unknown_case_is_404(client: TestClient) -> None:
    response = client.post(
        "/api/cases/no-such-case/ai-attempts", json={"provider": "gemini"}, headers=KEY
    )
    assert response.status_code == 404
    assert response.json()["title"] == "Case not found"


def test_unknown_model_is_422(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, recorded: list[dict[str, Any]]
) -> None:
    monkeypatch.delenv("PIPELINE_FAKE_LLM")
    response = post(client, model="claude-sonnet-5-5")
    assert response.status_code == 422 and response.json()["title"] == "Unknown model"
    assert recorded == []


def test_missing_credentials_is_503(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, recorded: list[dict[str, Any]]
) -> None:
    monkeypatch.delenv("PIPELINE_FAKE_LLM")
    response = post(client, provider="gemini")
    assert response.status_code == 503
    assert response.json()["title"] == "Model provider unavailable"
    assert response.json()["detail"] == NOT_AVAILABLE  # no env var names, no vendor names
    assert recorded == []


def test_quota_is_503_and_unusable_answers_are_502(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, recorded: list[dict[str, Any]]
) -> None:
    # The SDK's text stays in the server log; the client gets a fixed, provider-neutral line.
    error = ProviderUnavailable("429 RESOURCE_EXHAUSTED org-7f3 quota", retryable=True, status=429)
    quota = FakeProvider(script=[error])
    monkeypatch.setattr("app.routers.ai_players.get_provider", lambda *args: quota)
    with structlog.testing.capture_logs() as logs:
        response = post(client)
    assert response.status_code == 503
    assert response.json()["detail"] == BUSY
    assert "org-7f3" not in response.text
    assert any(entry.get("error") == str(error) for entry in logs)

    broken = FakeProvider(script=["{", "{"])
    monkeypatch.setattr("app.routers.ai_players.get_provider", lambda *args: broken)
    with structlog.testing.capture_logs() as logs:
        response = post(client)
    assert response.status_code == 502
    assert response.json()["detail"] == UNUSABLE
    assert "failed validation" not in response.text
    assert any("failed validation" in entry.get("error", "") for entry in logs)
    assert recorded == []  # nothing is stored when the model could not play


def test_a_rejected_request_is_502_without_the_provider_text(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, recorded: list[dict[str, Any]]
) -> None:
    raw = "provider rejected the request (400): org org-7f3 has exceeded the context window"
    rejecting = FakeProvider(script=[ProviderError(raw)])
    monkeypatch.setattr("app.routers.ai_players.get_provider", lambda *args: rejecting)
    with structlog.testing.capture_logs() as logs:
        response = post(client)
    assert response.status_code == 502
    assert response.json()["detail"] == UNUSABLE
    assert "org-7f3" not in response.text
    assert any(entry.get("error") == raw for entry in logs)
    assert recorded == []
