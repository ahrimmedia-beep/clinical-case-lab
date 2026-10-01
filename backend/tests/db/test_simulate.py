from __future__ import annotations

import json

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.repository.cases import insert_case
from app.schemas.case import ClinicalCase
from seeds.load import CASES_DIR, seed_files
from seeds.simulate_cohort import seed_slugs, simulate_case

pytestmark = pytest.mark.db

LAM = CASES_DIR / "03-lam.json"


async def test_simulate_case_is_idempotent_and_labelled(conn: AsyncConnection) -> None:
    created = await insert_case(conn, ClinicalCase.model_validate(json.loads(LAM.read_text())))
    assert await simulate_case(conn, created.slug, n=20, seed=1) == 20
    assert await simulate_case(conn, created.slug, n=20, seed=1) == 0  # resume: kept
    assert await simulate_case(conn, created.slug, n=20, seed=1, reset=True) == 20
    row = (
        await conn.execute(
            text(
                "SELECT count(*) AS total, bool_and(is_simulated) AS simulated, "
                "min(simulated_label) AS label, count(DISTINCT points) AS spread FROM attempts"
            )
        )
    ).one()
    await conn.rollback()
    assert (row.total, row.simulated, row.label) == (20, True, "cohort")
    assert row.spread >= 2


async def test_unknown_slug_raises_lookup_error(conn: AsyncConnection) -> None:
    with pytest.raises(LookupError, match="make seed"):
        await simulate_case(conn, "no-such-case", n=5, seed=1)


async def test_seed_slugs_match_what_the_api_assigns(client: httpx.AsyncClient) -> None:
    slugs = []
    for path in seed_files():
        response = await client.post("/api/cases", json=json.loads(path.read_text()))
        assert response.status_code == 201, response.text
        slugs.append(response.json()["slug"])
    assert slugs == seed_slugs()


async def test_real_attempt_lands_in_the_simulated_cohort(
    client: httpx.AsyncClient, conn: AsyncConnection
) -> None:
    slug = (await client.post("/api/cases", json=json.loads(LAM.read_text()))).json()["slug"]
    await simulate_case(conn, slug, n=30, seed=3)
    response = await client.post(
        f"/api/cases/{slug}/attempts",
        json={"choices": {"treatment": ["A", "B"]}, "diagnosis_text": "LAM", "confidence": 4},
    )
    body = response.json()
    assert response.status_code == 201, response.text
    assert (body["cohort_size"], body["cohort_is_simulated"]) == (31, True)
    assert body["percentile"] is not None
    assert sum(b["count"] for b in body["histogram"]) == 31


async def test_interrupted_cohort_resumes_with_the_same_attempts(conn: AsyncConnection) -> None:
    created = await insert_case(conn, ClinicalCase.model_validate(json.loads(LAM.read_text())))
    assert await simulate_case(conn, created.slug, n=5, seed=4) == 5
    assert await simulate_case(conn, created.slug, n=12, seed=4) == 7  # tops up, no duplicates
    resumed = (await conn.execute(text("SELECT points FROM attempts ORDER BY id"))).scalars().all()
    await conn.rollback()
    assert await simulate_case(conn, created.slug, n=12, seed=4, reset=True) == 12
    fresh = (await conn.execute(text("SELECT points FROM attempts ORDER BY id"))).scalars().all()
    await conn.rollback()
    assert resumed == fresh


async def test_seeded_catalogue_leads_with_the_hero_case(client: httpx.AsyncClient) -> None:
    for path in seed_files():
        assert (await client.post("/api/cases", json=json.loads(path.read_text()))).is_success
    listed = (await client.get("/api/cases")).json()
    assert listed[0]["title"] == "A second collapsed lung in a young non-smoker"  # LAM
    assert [c["review_status"] for c in listed] == ["approved"] * 3
