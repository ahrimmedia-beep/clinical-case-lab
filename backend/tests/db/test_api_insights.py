"""★3 sponsor insights: where the cohort goes wrong, computed in SQL over humans + cohort."""

from __future__ import annotations

import json
from collections import Counter

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncConnection

from app.config import get_settings
from app.repository.attempts import record_attempt
from app.repository.cases import insert_case
from app.schemas.attempt import AttemptIn, MultiSelectStage
from app.schemas.case import ClinicalCase
from app.scoring import score_attempt
from seeds.load import CASES_DIR
from seeds.simulate_cohort import case_rng, simulate_attempt, simulate_case

pytestmark = pytest.mark.db

LAM = ClinicalCase.model_validate(json.loads((CASES_DIR / "03-lam.json").read_text()))
N, SEED = 200, 11


async def seeded_lam(conn: AsyncConnection) -> str:
    created = await insert_case(conn, LAM)
    await simulate_case(conn, created.slug, n=N, seed=SEED)
    return created.slug


def expected_plays(slug: str) -> list[AttemptIn]:
    rng = case_rng(SEED, slug)
    return [simulate_attempt(LAM, rng) for _ in range(N)]


async def test_insights_match_the_cohort(client: httpx.AsyncClient, conn: AsyncConnection) -> None:
    slug = await seeded_lam(conn)
    plays = expected_plays(slug)
    response = await client.get(f"/api/cases/{slug}/insights")
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["slug"], body["title"]) == (slug, LAM.title)
    assert (body["cohort_size"], body["cohort_is_simulated"]) == (N, True)
    correct = [score_attempt(LAM, a).diagnosis.correct for a in plays]
    assert body["diagnosis_accuracy"] == pytest.approx(sum(correct) / N)

    assert [s["stage"] for s in body["stages"]] == [
        "interview",
        "differential",
        "workup",
        "treatment",
    ]
    for stage in body["stages"]:
        decision = next(d for d in LAM.decisions if d.stage == stage["stage"])
        key = MultiSelectStage(stage["stage"])
        picks = Counter(k for a in plays for k in set(a.choices.get(key, [])))
        assert [o["key"] for o in stage["options"]] == [o.key for o in decision.options]
        for option in stage["options"]:
            assert option["pick_rate"] == pytest.approx(picks[option["key"]] / N)
        missed = {m["key"]: m["missed_rate"] for m in stage["missed_correct"]}
        assert set(missed) == {o.key for o in decision.options if o.is_correct}
        for option in stage["options"]:
            if option["is_correct"]:
                assert missed[option["key"]] == pytest.approx(1 - option["pick_rate"])
        rates = [m["missed_rate"] for m in stage["missed_correct"]]
        assert rates == sorted(rates, reverse=True)  # most-missed first

    treatment = next(s for s in body["stages"] if s["stage"] == "treatment")
    harmful = next(o for o in treatment["options"] if o["is_harmful"])
    assert harmful["pick_rate"] > 0  # the cohort makes harmful picks, the sponsor sees them


async def test_key_test_effect_is_positive(
    client: httpx.AsyncClient, conn: AsyncConnection
) -> None:
    slug = await seeded_lam(conn)
    body = (await client.get(f"/api/cases/{slug}/insights")).json()
    workup = next(d for d in LAM.decisions if d.stage == "workup")
    assert [k["key"] for k in body["key_tests"]] == [o.key for o in workup.options if o.is_correct]
    for test in body["key_tests"]:
        assert 0 < test["chose_rate"] < 1
        assert test["dx_accuracy_if_chosen"] > test["dx_accuracy_if_not"], test


async def test_top_wrong_diagnoses_and_ai_exclusion(
    client: httpx.AsyncClient, conn: AsyncConnection
) -> None:
    slug = await seeded_lam(conn)
    before = (await client.get(f"/api/cases/{slug}/insights")).json()
    wrong = before["top_wrong_diagnoses"]
    assert wrong and len(wrong) <= 5
    assert [w["count"] for w in wrong] == sorted((w["count"] for w in wrong), reverse=True)
    assert all(w["text"] not in LAM.diagnosis_terms() for w in wrong)

    ai = AttemptIn.model_validate(
        {"choices": {"workup": ["E"]}, "diagnosis_text": "Sarcoidosis", "confidence": 5}
    )
    await record_attempt(conn, slug, ai, simulated_label="ai:claude-opus-5-5")
    after = (await client.get(f"/api/cases/{slug}/insights")).json()
    assert after["cohort_size"] == N
    assert after["stages"] == before["stages"]
    assert after["top_wrong_diagnoses"] == wrong
    assert [b["label"] for b in after["benchmarks"]] == ["ai:claude-opus-5-5"]


async def test_insights_without_attempts(client: httpx.AsyncClient, conn: AsyncConnection) -> None:
    created = await insert_case(conn, LAM)
    body = (await client.get(f"/api/cases/{created.slug}/insights")).json()
    assert (body["cohort_size"], body["cohort_is_simulated"]) == (0, False)
    assert body["diagnosis_accuracy"] is None and body["top_wrong_diagnoses"] == []
    assert all(o["pick_rate"] == 0 for s in body["stages"] for o in s["options"])
    assert all(k["dx_accuracy_if_chosen"] is None for k in body["key_tests"])


async def test_unknown_case_is_404(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/cases/no-such-case/insights")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")


async def test_insights_require_the_internal_key(
    client: httpx.AsyncClient, conn: AsyncConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    created = await insert_case(conn, LAM)
    monkeypatch.setenv("INTERNAL_API_KEY", "s3cret")
    get_settings.cache_clear()
    url = f"/api/cases/{created.slug}/insights"
    assert (await client.get(url)).status_code == 401
    assert (await client.get(url, headers={"X-Internal-Key": "s3cret"})).status_code == 200
