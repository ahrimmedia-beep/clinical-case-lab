from __future__ import annotations

import copy
import json
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.config import get_settings

pytestmark = pytest.mark.db

COUNTS_SQL = text(
    "SELECT (SELECT count(*) FROM cases) AS cases, "
    "(SELECT count(*) FROM case_findings) AS findings, "
    "(SELECT count(*) FROM decision_options) AS options, "
    "(SELECT count(*) FROM decision_accepted_answers) AS accepted"
)


def reorder(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: reorder(value[k]) for k in reversed(list(value))}
    if isinstance(value, list):
        return [reorder(v) for v in value]
    return value


async def counts(engine: AsyncEngine) -> dict[str, int]:
    async with engine.connect() as conn:
        return dict((await conn.execute(COUNTS_SQL)).mappings().one())


async def create(client: httpx.AsyncClient, case: dict[str, Any]) -> dict[str, Any]:
    response = await client.post("/api/cases", json=case)
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


async def test_create_case_returns_201_and_location(
    client: httpx.AsyncClient, case_pe: dict[str, Any]
) -> None:
    response = await client.post("/api/cases", json=case_pe)
    assert response.status_code == 201
    body = response.json()
    assert body["created"] is True and body["id"] >= 1
    assert response.headers["location"] == f"/api/cases/{body['slug']}"


async def test_duplicate_case_with_reordered_keys_returns_200_without_new_rows(
    client: httpx.AsyncClient, engine: AsyncEngine, case_pe: dict[str, Any]
) -> None:
    first = await create(client, case_pe)
    before = await counts(engine)
    twin = reorder(copy.deepcopy(case_pe))
    twin["title"] = f"  {twin['title']}  "
    response = await client.post(
        "/api/cases",
        content=json.dumps(twin, indent=4),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["id"], body["slug"], body["created"]) == (first["id"], first["slug"], False)
    assert "location" not in response.headers
    assert (
        await counts(engine) == before == {"cases": 1, "findings": 5, "options": 12, "accepted": 3}
    )


async def test_invalid_case_is_422_problem(
    client: httpx.AsyncClient, case_pe: dict[str, Any]
) -> None:
    leaky = copy.deepcopy(case_pe)
    leaky["title"] = "A classic pulmonary embolism"
    response = await client.post("/api/cases", json=leaky)
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")


async def test_list_and_get_case(client: httpx.AsyncClient, case_pe: dict[str, Any]) -> None:
    created = await create(client, case_pe)
    listed = (await client.get("/api/cases")).json()
    assert [c["slug"] for c in listed] == [created["slug"]]
    assert listed[0]["decision_count"] == 5
    response = await client.get(f"/api/cases/{created['slug']}")
    assert response.status_code == 200
    body = response.json()
    assert [s["key"] for s in body["stages"]][:3] == [
        "presenting_complaint",
        "history",
        "interview",
    ]
    for secret in (
        '"is_correct"',
        '"accepted_answers"',
        "Thrombolysis is reserved",
        "Haemodynamically stable",
        "Yes, a 14-hour flight yesterday.",
    ):
        assert secret not in response.text, secret


async def test_unknown_case_is_404_problem(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/cases/no-such-case")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["title"] == "Case not found"


async def test_reveal_returns_chosen_reveals_only(
    client: httpx.AsyncClient, case_pe: dict[str, Any]
) -> None:
    slug = (await create(client, case_pe))["slug"]
    response = await client.post(
        f"/api/cases/{slug}/reveal", json={"stage": "workup", "option_keys": ["A", "C"]}
    )
    assert response.status_code == 200
    assert response.json() == [
        {"key": "A", "reveal": "Filling defect in the right lower lobe pulmonary artery."},
        {"key": "C", "reveal": "Not performed."},
    ]
    bad = await client.post(
        f"/api/cases/{slug}/reveal", json={"stage": "workup", "option_keys": ["F"]}
    )
    assert bad.status_code == 422
    assert "option 'F' does not exist in stage 'workup'" in bad.json()["detail"]


async def test_reveal_for_a_stage_the_case_lacks_is_422(
    client: httpx.AsyncClient, case_pe: dict[str, Any]
) -> None:
    data = copy.deepcopy(case_pe)
    data["decisions"] = [d for d in data["decisions"] if d["stage"] != "interview"]
    slug = (await create(client, data))["slug"]
    response = await client.post(
        f"/api/cases/{slug}/reveal", json={"stage": "interview", "option_keys": ["A"]}
    )
    assert response.status_code == 422
    assert "stage 'interview' is not part of this case" in response.json()["detail"]


async def test_readyz_with_database(client: httpx.AsyncClient) -> None:
    response = await client.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_llm_case_is_listed_and_served_as_a_draft(
    client: httpx.AsyncClient, case_pe: dict[str, Any]
) -> None:
    source = {"kind": "llm", "provider": "claude", "model": "claude-opus-5-5", "text": "raw text"}
    created = await create(client, {**case_pe, "source": source})
    listed = (await client.get("/api/cases")).json()
    assert [(c["slug"], c["review_status"], c["source_kind"]) for c in listed] == [
        (created["slug"], "draft", "llm")
    ]
    response = await client.get(f"/api/cases/{created['slug']}")
    assert response.json()["review_status"] == "draft"
    assert "raw text" not in response.text


async def test_ingest_with_the_key_when_required(
    client: httpx.AsyncClient, case_pe: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REQUIRE_INGEST_KEY", "true")
    monkeypatch.setenv("INTERNAL_API_KEY", "s3cret")
    get_settings.cache_clear()
    assert (await client.post("/api/cases", json=case_pe)).status_code == 401
    keyed = await client.post("/api/cases", json=case_pe, headers={"X-Internal-Key": "s3cret"})
    assert keyed.status_code == 201
