from __future__ import annotations

import copy
import json
import re
import string
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.case_views import build_case_public
from app.schemas.attempt import AttemptIn, MultiSelectStage
from app.schemas.case import ClinicalCase
from app.scoring import score_attempt, unknown_choices
from app.stages import MULTI_SELECT_STAGES, Stage
from app.textnorm import contains_term
from seeds import load as seed_load
from seeds.simulate_cohort import case_rng, seed_slugs, simulate_attempt

SEED_FILES = seed_load.seed_files()
KEYS = string.ascii_uppercase


def load(path: Path) -> ClinicalCase:
    return ClinicalCase.model_validate(json.loads(path.read_text(encoding="utf-8")))


def test_three_seed_cases_exist_and_the_hero_loads_last() -> None:
    # The catalogue lists newest first, so the last file loaded (LAM) leads it as the hero.
    assert [p.name for p in SEED_FILES] == ["01-pe.json", "02-aatd.json", "03-lam.json"]


def _options_unordered(data: dict[str, Any]) -> dict[str, Any]:
    """The case with each decision's options as an order-free list (keys dropped)."""
    out = copy.deepcopy(data)
    for decision in out["decisions"]:
        unkeyed = ({k: v for k, v in o.items() if k != "key"} for o in decision["options"])
        decision["options"] = sorted(unkeyed, key=lambda o: o["text"])
    return out


def test_pe_seed_is_the_foundation_fixture_with_shuffled_options() -> None:
    # The tests pin the fixture's keys; the seed carries the same content in shuffled order.
    fixture = json.loads((Path(__file__).parent / "fixtures" / "case_pe.json").read_text())
    seed = json.loads(SEED_FILES[0].read_text())
    assert _options_unordered(seed) == _options_unordered(fixture)
    assert seed != fixture


@pytest.mark.parametrize("path", SEED_FILES, ids=lambda p: p.name)
def test_no_seed_decision_lists_its_correct_options_first(path: Path) -> None:
    # Spec §6.2: option order must not give the key away (review C1: it did in all 12).
    for decision in load(path).decisions:
        if not decision.options:
            continue
        correct = [o.is_correct for o in decision.options]
        leading = [True] * sum(correct) + [False] * (len(correct) - sum(correct))
        assert correct != leading, f"{path.name} {decision.stage}: correct options come first"
        assert [o.key for o in decision.options] == list(KEYS[: len(correct)])  # re-lettered


@pytest.mark.parametrize("path", SEED_FILES, ids=lambda p: p.name)
def test_reveals_and_option_texts_do_not_name_the_diagnosis(path: Path) -> None:
    case = load(path)  # also proves the file is a valid ClinicalCase (no-leak rules included)
    terms = case.diagnosis_terms()
    for decision in case.decisions:
        for option in decision.options:
            texts = [option.reveal or ""]
            if decision.stage != "differential":  # listing the diagnosis there is the point
                texts.append(option.text)
            for text in texts:
                for term in terms:
                    assert not contains_term(text, term), f"{path.name}: {text!r} names {term!r}"


@pytest.mark.parametrize("name", ["02-aatd.json", "03-lam.json"])
def test_rare_disease_seeds_show_a_withheld_result(name: str) -> None:
    public = build_case_public(1, "seed-abc123", load(seed_load.CASES_DIR / name))
    withheld = [item for stage in public.stages for item in stage.items if item.withheld]
    assert len(withheld) == 1


@pytest.mark.parametrize("path", SEED_FILES, ids=lambda p: p.name)
def test_perfect_play_scores_full_marks(path: Path) -> None:
    case = load(path)
    choices = {
        d.stage.value: [o.key for o in d.options if o.is_correct]
        for d in case.decisions
        if Stage(d.stage) in MULTI_SELECT_STAGES
    }
    attempt = AttemptIn.model_validate(
        {"choices": choices, "diagnosis_text": case.final_diagnosis.name, "confidence": 5}
    )
    score = score_attempt(case, attempt)
    assert score.points == score.max_points
    assert (score.wrong, score.missed, score.harmful) == (0, 0, 0)


def test_simulation_is_deterministic_valid_and_spread() -> None:
    case = load(seed_load.CASES_DIR / "03-lam.json")
    rng, again_rng = case_rng(7, "lam"), case_rng(7, "lam")
    first = [simulate_attempt(case, rng) for _ in range(200)]
    again = [simulate_attempt(case, again_rng) for _ in range(200)]
    assert first == again
    assert all(unknown_choices(case, a.choices) == [] for a in first)
    points = [score_attempt(case, a).points for a in first]
    max_points = score_attempt(case, first[0]).max_points
    assert len(set(points)) >= 3
    assert 0.3 * max_points <= sum(points) / len(points) <= 0.9 * max_points


def test_seed_slugs_are_url_safe() -> None:
    slugs = seed_slugs()
    assert len(slugs) == 3
    assert all(re.fullmatch(r"[a-z0-9-]{3,100}", s) for s in slugs)
    assert slugs[0].startswith("sudden-breathlessness-after-a-long-flight-")


def test_load_seeds_posts_every_file_and_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(seed_load, "sleep", lambda _seconds: None)
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if len(calls) == 1:
            return httpx.Response(503)
        created = len(calls) != 3
        body = {"id": len(calls), "slug": f"case-{len(calls)}", "created": created}
        return httpx.Response(201 if created else 200, json=body)

    with httpx.Client(transport=httpx.MockTransport(handler), base_url="http://api") as client:
        results = seed_load.load_seeds(client, SEED_FILES)
    assert calls == ["/api/cases"] * 4
    assert [status for _, status in results] == ["created", "exists", "created"]


def test_load_seeds_stops_on_a_rejected_case() -> None:
    transport = httpx.MockTransport(lambda _r: httpx.Response(422, json={"title": "Invalid"}))
    with httpx.Client(transport=transport, base_url="http://api") as client:
        with pytest.raises(SystemExit, match="HTTP 422"):
            seed_load.load_seeds(client, SEED_FILES[:1])


def test_load_seeds_sends_the_internal_key(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("x-internal-key"))
        return httpx.Response(201, json={"id": 1, "slug": "case-1", "created": True})

    transport = httpx.MockTransport(handler)
    with seed_load.api_client("http://api", "s3cret", transport=transport) as client:
        seed_load.load_seeds(client, SEED_FILES[:1])
    with seed_load.api_client("http://api", None, transport=transport) as client:
        seed_load.load_seeds(client, SEED_FILES[:1])
    assert seen == ["s3cret", None]


# ---------- causal cohort (spec §9, amendments §C) ----------


def _cohort(name: str, n: int = 400, seed: int = 2026) -> tuple[ClinicalCase, list[AttemptIn]]:
    case = load(seed_load.CASES_DIR / name)
    rng = case_rng(seed, name)
    return case, [simulate_attempt(case, rng) for _ in range(n)]


def _ordered_key_test(case: ClinicalCase, attempt: AttemptIn) -> bool:
    workup = next(d for d in case.decisions if d.stage == "workup")
    correct = {o.key for o in workup.options if o.is_correct}
    return bool(correct & set(attempt.choices.get(MultiSelectStage.WORKUP, [])))


@pytest.mark.parametrize("name", ["01-pe.json", "02-aatd.json", "03-lam.json"])
def test_cohort_is_causal_ordering_the_key_test_raises_accuracy(name: str) -> None:
    case, plays = _cohort(name)
    ordered = [a for a in plays if _ordered_key_test(case, a)]
    skipped = [a for a in plays if not _ordered_key_test(case, a)]
    assert len(ordered) >= 80 and len(skipped) >= 80  # both groups are well populated

    def accuracy(group: list[AttemptIn]) -> float:
        return sum(score_attempt(case, a).diagnosis.correct for a in group) / len(group)

    # Policy: P(right diagnosis) = 0.8 if a correct work-up option was ordered, else 0.3.
    assert 0.68 <= accuracy(ordered) <= 0.92
    assert 0.18 <= accuracy(skipped) <= 0.42


def test_cohort_treatment_shows_the_anti_gaming_rules() -> None:
    case, plays = _cohort("03-lam.json")
    treatments = [score_attempt(case, a).stages[Stage.TREATMENT] for a in plays]
    harmful = [t for t in treatments if t.harmful]
    wrong_only = [t for t in treatments if t.wrong and not t.harmful]
    assert len(harmful) >= 20 and all(t.points == 0 for t in harmful)
    assert len(wrong_only) >= 20 and all(t.points == max(0, t.right - t.wrong) for t in wrong_only)
