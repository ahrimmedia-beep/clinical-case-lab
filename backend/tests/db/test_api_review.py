"""★2 review gate over HTTP: draft → review → approve (once)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest

from app.config import get_settings

pytestmark = pytest.mark.db

SOURCE = "Sudden breathlessness after a 14-hour flight; left calf is swollen and tender."


async def create(client: httpx.AsyncClient, case: dict[str, Any]) -> str:
    response = await client.post("/api/cases", json=case)
    assert response.status_code == 201, response.text
    slug: str = response.json()["slug"]
    return slug


def draft(case_pe: dict[str, Any]) -> dict[str, Any]:
    return {**case_pe, "source": {"kind": "llm", "provider": "claude", "text": SOURCE}}


async def test_draft_review_then_approve_once(
    client: httpx.AsyncClient, case_pe: dict[str, Any]
) -> None:
    slug = await create(client, draft(case_pe))
    review = await client.get(f"/api/cases/{slug}/review")
    assert review.status_code == 200, review.text
    body = review.json()
    assert body["review_status"] == "draft" and body["source"]["provider"] == "claude"
    assert "text" not in body["source"]
    assert body["answer_key"]["final_diagnosis"]["name"] == "Pulmonary embolism"
    grounding = next(c for c in body["checklist"] if c["id"] == "grounding")
    assert grounding["status"] == "warn"  # most PE fixture quotes are not in this short source

    before = datetime.now(UTC) - timedelta(seconds=5)
    approved = await client.post(f"/api/cases/{slug}/approve")
    assert approved.status_code == 200, approved.text
    result = approved.json()
    assert (result["slug"], result["review_status"]) == (slug, "approved")
    assert datetime.fromisoformat(result["reviewed_at"]) >= before

    again = await client.post(f"/api/cases/{slug}/approve")
    assert again.status_code == 409
    assert again.headers["content-type"].startswith("application/problem+json")

    public = (await client.get(f"/api/cases/{slug}")).json()
    assert public["review_status"] == "approved"
    listed = (await client.get("/api/cases")).json()
    assert listed[0]["review_status"] == "approved"
    reviewed = (await client.get(f"/api/cases/{slug}/review")).json()
    assert reviewed["review_status"] == "approved"


async def test_approving_a_manual_case_is_409(
    client: httpx.AsyncClient, case_pe: dict[str, Any]
) -> None:
    slug = await create(client, case_pe)
    assert (await client.post(f"/api/cases/{slug}/approve")).status_code == 409


async def test_unknown_case_is_404(client: httpx.AsyncClient) -> None:
    for response in (
        await client.get("/api/cases/no-such-case/review"),
        await client.post("/api/cases/no-such-case/approve"),
    ):
        assert response.status_code == 404
        assert response.json()["title"] == "Case not found"


async def test_review_and_approve_require_the_internal_key(
    client: httpx.AsyncClient, case_pe: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    slug = await create(client, draft(case_pe))
    monkeypatch.setenv("INTERNAL_API_KEY", "s3cret")
    get_settings.cache_clear()
    assert (await client.get(f"/api/cases/{slug}/review")).status_code == 401
    assert (await client.post(f"/api/cases/{slug}/approve")).status_code == 401
    keyed = {"X-Internal-Key": "s3cret"}
    assert (await client.get(f"/api/cases/{slug}/review", headers=keyed)).status_code == 200
    assert (await client.post(f"/api/cases/{slug}/approve", headers=keyed)).status_code == 200


async def test_a_failing_check_blocks_approval_on_the_server(
    client: httpx.AsyncClient, case_pe: dict[str, Any]
) -> None:
    # The page disables the sign-off box on a FAIL, but the API is the gate: a Server Action is a
    # public POST endpoint, so the checklist is recomputed here before the draft is promoted.
    leaky = {**case_pe, "source": {**draft(case_pe)["source"], "text": f"{SOURCE} jd@example.com"}}
    slug = await create(client, leaky)
    checklist = (await client.get(f"/api/cases/{slug}/review")).json()["checklist"]
    assert next(c for c in checklist if c["id"] == "phi")["status"] == "fail"

    refused = await client.post(f"/api/cases/{slug}/approve")
    assert refused.status_code == 409
    assert refused.headers["content-type"].startswith("application/problem+json")
    body = refused.json()
    assert body["title"] == "Review checks failing"
    assert "No identifiers in the source text" in body["detail"]
    assert (await client.get(f"/api/cases/{slug}")).json()["review_status"] == "draft"
