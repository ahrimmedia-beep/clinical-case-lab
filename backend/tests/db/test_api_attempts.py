from __future__ import annotations

import copy
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.problems import ProblemError
from app.repository.attempts import load_case_key, record_attempt
from app.schemas.attempt import AttemptIn

pytestmark = pytest.mark.db

PERFECT = {
    "interview": ["A", "B"],
    "differential": ["A", "B"],
    "workup": ["A", "B"],
    "treatment": ["A", "B"],
}


async def create_case(client: httpx.AsyncClient, case: dict[str, Any]) -> str:
    response = await client.post("/api/cases", json=case)
    assert response.status_code == 201, response.text
    slug: str = response.json()["slug"]
    return slug


async def play(
    client: httpx.AsyncClient,
    slug: str,
    choices: dict[str, list[str]],
    dx: str,
    confidence: int = 3,
) -> httpx.Response:
    return await client.post(
        f"/api/cases/{slug}/attempts",
        json={
            "choices": choices,
            "diagnosis_text": dx,
            "confidence": confidence,
            "duration_ms": 240_000,
        },
    )


async def attempt_count(engine: AsyncEngine) -> int:
    async with engine.connect() as conn:
        return int(await conn.scalar(text("SELECT count(*) FROM attempts")) or 0)


def percent_rank(scores: list[tuple[int, int]], mine: tuple[int, int]) -> float:
    """Python reference for PostgreSQL percent_rank(): (rank - 1) / (n - 1)."""
    below = sum(1 for s in scores if s < mine)
    return round(100 * below / (len(scores) - 1), 1)


async def test_perfect_attempt_returns_a_full_debrief(
    client: httpx.AsyncClient, case_pe: dict[str, Any]
) -> None:
    slug = await create_case(client, case_pe)
    response = await play(client, slug, PERFECT, "Pulmonary embolism", confidence=4)
    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["points"], body["max_points"]) == (3, 3)
    assert (body["right"], body["wrong"], body["missed"], body["harmful"]) == (9, 0, 0, 0)
    assert body["total_decisions"] == 9 and body["case_slug"] == slug
    assert body["percentile"] is None  # cohort of 1 < 5
    assert (body["cohort_size"], body["cohort_is_simulated"]) == (1, False)
    assert body["histogram"] == [
        {"points": 0, "count": 0},
        {"points": 1, "count": 0},
        {"points": 2, "count": 0},
        {"points": 3, "count": 1},
    ]
    assert body["final_diagnosis"]["name"] == "Pulmonary embolism"
    assert body["diagnosis"]["correct"] is True
    assert body["diagnosis"]["calibration"] == "calibrated"
    assert len(body["stages"]) == 9
    workup = next(s for s in body["stages"] if s["key"] == "workup")
    option_a = next(o for o in workup["options"] if o["key"] == "A")
    assert (option_a["state"], option_a["pick_rate"]) == ("right", 1.0)
    assert option_a["reveal"] == "Filling defect in the right lower lobe pulmonary artery."


async def test_unknown_option_key_is_422_and_names_it(
    client: httpx.AsyncClient, engine: AsyncEngine, case_pe: dict[str, Any]
) -> None:
    slug = await create_case(client, case_pe)
    response = await play(client, slug, {"workup": ["A", "F"]}, "PE")
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert "option 'F' does not exist in stage 'workup'" in response.json()["detail"]
    assert await attempt_count(engine) == 0  # rolled back, nothing stored


async def test_stage_missing_from_case_is_422(
    client: httpx.AsyncClient, engine: AsyncEngine, case_pe: dict[str, Any]
) -> None:
    data = copy.deepcopy(case_pe)
    data["decisions"] = [d for d in data["decisions"] if d["stage"] != "interview"]
    slug = await create_case(client, data)
    response = await play(client, slug, {"interview": ["A"]}, "PE")
    assert response.status_code == 422
    assert "stage 'interview' is not part of this case" in response.json()["detail"]
    assert await attempt_count(engine) == 0


@pytest.mark.parametrize(
    "choices",
    [{"workup": ["Z"]}, {"diagnosis": ["A"]}, {"workup": ["AA"]}],
)
async def test_malformed_choices_are_422(
    client: httpx.AsyncClient, case_pe: dict[str, Any], choices: dict[str, list[str]]
) -> None:
    slug = await create_case(client, case_pe)
    response = await play(client, slug, choices, "PE")
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")


async def test_unknown_case_is_404(client: httpx.AsyncClient) -> None:
    response = await play(client, "no-such-case", {}, "PE")
    assert response.status_code == 404
    assert response.json()["title"] == "Case not found"


async def test_duplicate_keys_are_stored_once(
    client: httpx.AsyncClient, case_pe: dict[str, Any]
) -> None:
    slug = await create_case(client, case_pe)
    response = await play(client, slug, {"workup": ["A", "A"]}, "PE")
    assert response.status_code == 201
    workup = next(s for s in response.json()["stages"] if s["key"] == "workup")
    assert workup["right"] == 1


async def test_percentile_histogram_and_pick_rates(
    client: httpx.AsyncClient, case_pe: dict[str, Any]
) -> None:
    slug = await create_case(client, case_pe)
    plays: list[tuple[dict[str, list[str]], str]] = [
        ({}, ""),  # (0, 0)
        ({}, "PE"),  # (1, 1)
        ({"workup": ["A"]}, "PE"),  # (1, 2)
        ({"treatment": ["A"]}, "PE"),  # (2, 2)
        (PERFECT, "PE"),  # (3, 9)
        ({"treatment": ["A"], "workup": ["A"]}, "PE"),  # (2, 3)
    ]
    scores: list[tuple[int, int]] = []
    bodies: list[dict[str, Any]] = []
    for choices, dx in plays:
        response = await play(client, slug, choices, dx)
        assert response.status_code == 201, response.text
        body = response.json()
        bodies.append(body)
        scores.append((body["points"], body["right"]))
    assert [b["percentile"] for b in bodies[:4]] == [None, None, None, None]
    assert bodies[4]["percentile"] == percent_rank(scores[:5], scores[4]) == 100.0
    assert bodies[5]["percentile"] == percent_rank(scores, scores[5]) == 80.0
    assert bodies[5]["cohort_size"] == 6
    assert bodies[5]["histogram"] == [
        {"points": 0, "count": 1},
        {"points": 1, "count": 2},
        {"points": 2, "count": 2},
        {"points": 3, "count": 1},
    ]
    workup = next(s for s in bodies[5]["stages"] if s["key"] == "workup")
    rates = {o["key"]: o["pick_rate"] for o in workup["options"]}
    assert rates["A"] == pytest.approx(3 / 6)  # plays 3, 5 and 6 chose workup A
    assert rates["C"] == 0.0


async def test_simulated_cohort_is_flagged(
    client: httpx.AsyncClient, conn: AsyncConnection, case_pe: dict[str, Any]
) -> None:
    slug = await create_case(client, case_pe)
    bot = AttemptIn.model_validate(
        {"choices": {"workup": ["A"]}, "diagnosis_text": "PE", "confidence": 3}
    )
    for _ in range(5):
        await record_attempt(conn, slug, bot, simulated_label="cohort")
    body = (await play(client, slug, PERFECT, "PE")).json()
    assert body["cohort_is_simulated"] is True
    assert body["cohort_size"] == 6
    assert body["percentile"] == 100.0


# ---------- record_attempt: the single scoring + storing path (humans, cohort, AI) ----------


AI_PLAY = AttemptIn.model_validate(
    {
        "choices": {"workup": ["C"], "treatment": ["A", "B", "C"]},
        "diagnosis_text": "Pulmonary embolism",
        "confidence": 5,
    }
)


async def test_record_attempt_scores_and_stores_server_side(
    client: httpx.AsyncClient, conn: AsyncConnection, case_pe: dict[str, Any]
) -> None:
    slug = await create_case(client, case_pe)
    recorded = await record_attempt(conn, slug, AI_PLAY, simulated_label="ai:claude-opus-4-8")
    assert recorded.slug == slug and recorded.attempt_id >= 1
    assert (recorded.score.points, recorded.score.max_points) == (1, 3)  # harmful C zeroes plan
    assert recorded.score.diagnosis.correct is True
    row = (
        await conn.execute(
            text(
                "SELECT is_simulated, simulated_label, points, harmful_count, "
                "(SELECT count(*) FROM attempt_choices) AS choices FROM attempts"
            )
        )
    ).one()
    await conn.rollback()
    assert tuple(row) == (True, "ai:claude-opus-4-8", 1, 1, 4)


async def test_record_attempt_rejects_unknown_cases_and_keys(
    client: httpx.AsyncClient, engine: AsyncEngine, conn: AsyncConnection, case_pe: dict[str, Any]
) -> None:
    slug = await create_case(client, case_pe)
    with pytest.raises(ProblemError) as missing:
        await record_attempt(conn, "no-such-case", AI_PLAY)
    assert missing.value.status == 404
    bad = AttemptIn.model_validate({"choices": {"workup": ["F"]}, "confidence": 3})
    with pytest.raises(ProblemError) as invalid:
        await record_attempt(conn, slug, bad)
    assert invalid.value.status == 422 and "option 'F'" in (invalid.value.detail or "")
    assert await attempt_count(engine) == 0


async def test_record_attempt_accepts_a_preloaded_case_key(
    client: httpx.AsyncClient, engine: AsyncEngine, conn: AsyncConnection, case_pe: dict[str, Any]
) -> None:
    slug = await create_case(client, case_pe)
    async with conn.begin():
        key = await load_case_key(conn, slug)
    assert key is not None and key.slug == slug
    for _ in range(3):
        await record_attempt(conn, key, AI_PLAY, simulated_label="cohort")
    assert await attempt_count(engine) == 3


async def test_ai_attempts_are_benchmarks_not_cohort(
    client: httpx.AsyncClient, conn: AsyncConnection, case_pe: dict[str, Any]
) -> None:
    slug = await create_case(client, case_pe)
    cohort_play = AttemptIn.model_validate(
        {"choices": {"workup": ["B"]}, "diagnosis_text": "asthma", "confidence": 2}
    )
    for _ in range(5):
        await record_attempt(conn, slug, cohort_play, simulated_label="cohort")
    older = AttemptIn.model_validate({"diagnosis_text": "pneumonia", "confidence": 4})
    await record_attempt(conn, slug, older, simulated_label="ai:claude-opus-4-8")
    await record_attempt(conn, slug, AI_PLAY, simulated_label="ai:claude-opus-4-8")
    await record_attempt(conn, slug, older, simulated_label="ai:gemini-3.8-flash")

    body = (await play(client, slug, PERFECT, "PE")).json()
    # Cohort = 5 simulated + this human; the three AI attempts are excluded everywhere.
    assert body["cohort_size"] == 6
    assert sum(b["count"] for b in body["histogram"]) == 6
    assert body["percentile"] == 100.0
    workup = next(s for s in body["stages"] if s["key"] == "workup")
    rates = {o["key"]: o["pick_rate"] for o in workup["options"]}
    assert rates == {"A": pytest.approx(1 / 6), "B": pytest.approx(6 / 6), "C": 0.0}
    # Benchmarks: the latest attempt per AI label.
    assert body["benchmarks"] == [
        {
            "label": "ai:claude-opus-4-8",
            "provider": "claude",
            "model": "claude-opus-4-8",
            "points": 1,
            "max_points": 3,
            "diagnosis_correct": True,
            "confidence": 5,
            "calibration": "calibrated",
        },
        {
            "label": "ai:gemini-3.8-flash",
            "provider": "gemini",
            "model": "gemini-3.8-flash",
            "points": 0,
            "max_points": 3,
            "diagnosis_correct": False,
            "confidence": 4,
            "calibration": "overconfident",
        },
    ]
    listed = (await client.get("/api/cases")).json()
    assert listed[0]["attempts_count"] == 6  # AI players are not counted as attempts


async def test_hedged_diagnosis_through_the_api(
    client: httpx.AsyncClient, case_pe: dict[str, Any]
) -> None:
    slug = await create_case(client, case_pe)
    body = (await play(client, slug, {}, "PE or pneumonia", confidence=5)).json()
    assert body["diagnosis"]["hedged"] is True
    assert body["diagnosis"]["correct"] is False
    assert body["points"] == 0


async def test_select_all_treatment_scores_nothing_through_the_api(
    client: httpx.AsyncClient, case_pe: dict[str, Any]
) -> None:
    slug = await create_case(client, case_pe)
    body = (await play(client, slug, {"treatment": ["A", "B", "C"]}, "PE")).json()
    treatment = next(s for s in body["stages"] if s["key"] == "treatment")
    assert (treatment["points"], body["points"], body["harmful"]) == (0, 1, 1)
