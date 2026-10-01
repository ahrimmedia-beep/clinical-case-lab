"""Insert a labelled simulated cohort for the showcase cases (is_simulated, label "cohort").

The percentile card needs a cohort and a fresh deploy has none. The UI labels these attempts
"simulated cohort". Every attempt goes through `record_attempt`, the same scoring + storing path
as a physician's.

The policy is causal, not uniform (spec §9): a simulated physician who ordered one of the case's
correct work-up tests names the right diagnosis with probability 0.8, one who did not with 0.3,
so the sponsor insights show a real key-test effect. Treatment plans include some wrong and
harmful picks, so the anti-gaming rules are visible in the distribution.

Resumable: attempts for a case are a deterministic sequence (seeded per case), and a run only
adds the ones still missing, so an interrupted run continues where it stopped (--reset rebuilds).

Usage (from backend/): uv run python -m seeds.simulate_cohort --n 200 [--seed 2026] [--reset]
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import random
import sys

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncConnection

from app.config import get_settings
from app.db.engine import make_engine
from app.db.tables import attempts
from app.repository.attempts import COHORT_LABEL, load_case_key, record_attempt
from app.repository.cases import content_hash, make_slug
from app.schemas.attempt import AttemptIn
from app.schemas.case import ClinicalCase, Decision
from app.stages import Stage
from seeds.load import seed_files

FALLBACK_WRONG = ("Community-acquired pneumonia", "Anxiety disorder", "Heart failure")
P_RIGHT_IF_KEY_TEST = 0.8
P_RIGHT_WITHOUT_KEY_TEST = 0.3


def case_rng(seed: int, slug: str) -> random.Random:
    digest = hashlib.sha256(f"{seed}:{slug}".encode()).hexdigest()
    return random.Random(int(digest[:16], 16))


def _pick(
    decision: Decision, rng: random.Random, *, right: float, wrong: float, harmful: float
) -> list[str]:
    return [
        o.key
        for o in decision.options
        if rng.random() < (right if o.is_correct else harmful if o.is_harmful else wrong)
    ]


def _workup(decision: Decision, rng: random.Random, skill: float, ordered_key: bool) -> list[str]:
    correct = [o.key for o in decision.options if o.is_correct]
    others = [o for o in decision.options if not o.is_correct]
    picked: list[str] = []
    if ordered_key:
        picked = [k for k in correct if rng.random() < 0.35 + 0.6 * skill] or [rng.choice(correct)]
    picked += [o.key for o in others if rng.random() < 0.15 + 0.45 * (1 - skill)]
    return sorted(picked)


def _wrong_diagnosis(case: ClinicalCase, rng: random.Random) -> str:
    final = case.diagnosis_terms()
    pool = [d.name for d in case.differential if d.name not in final] or list(FALLBACK_WRONG)
    return rng.choice(pool)


def simulate_attempt(case: ClinicalCase, rng: random.Random) -> AttemptIn:
    """One plausible physician. Skill ~ Beta(4, 2.5): mean ~0.62 with a long weak tail."""
    skill = rng.betavariate(4.0, 2.5)
    ordered_key = rng.random() < 0.3 + 0.5 * skill  # ~0.6 of the cohort orders a key test
    choices: dict[str, list[str]] = {}
    for decision in case.decisions:
        stage = Stage(decision.stage)
        if stage is Stage.WORKUP:
            choices[stage.value] = _workup(decision, rng, skill, ordered_key)
        elif stage is Stage.TREATMENT:
            choices[stage.value] = _pick(
                decision,
                rng,
                right=0.35 + 0.6 * skill,
                wrong=0.1 + 0.45 * (1 - skill),
                harmful=0.05 + 0.3 * (1 - skill),
            )
        elif stage is not Stage.DIAGNOSIS:
            choices[stage.value] = _pick(
                decision, rng, right=0.25 + 0.7 * skill, wrong=0.4 * (1 - skill), harmful=0.1
            )
    p_right = P_RIGHT_IF_KEY_TEST if ordered_key else P_RIGHT_WITHOUT_KEY_TEST
    roll = rng.random()
    if roll < 0.03:
        diagnosis = ""
    elif roll < 0.03 + 0.97 * p_right:
        diagnosis = rng.choice(case.diagnosis_terms())
    else:
        diagnosis = _wrong_diagnosis(case, rng)
    confidence = max(1, min(5, round(1 + 4 * skill + rng.gauss(0, 0.9))))
    return AttemptIn.model_validate(
        {
            "choices": choices,
            "diagnosis_text": diagnosis,
            "confidence": confidence,
            "duration_ms": int(rng.uniform(4, 18) * 60_000),
        }
    )


def seed_slugs() -> list[str]:
    """The slugs the API assigns to the seed files (slug = title + content-hash prefix)."""
    slugs: list[str] = []
    for path in seed_files():
        case = ClinicalCase.model_validate(json.loads(path.read_text(encoding="utf-8")))
        slugs.append(make_slug(case.title, content_hash(case)))
    return slugs


async def simulate_case(
    conn: AsyncConnection, slug: str, *, n: int, seed: int, reset: bool = False
) -> int:
    """Bring the case's simulated cohort up to `n` attempts; returns how many were added."""
    async with conn.begin():
        key = await load_case_key(conn, slug)
        if key is None:
            raise LookupError(f"no case with slug {slug!r}; run `make seed` first")
        cohort = (attempts.c.case_id == key.case_id) & (attempts.c.simulated_label == COHORT_LABEL)
        if reset:
            await conn.execute(delete(attempts).where(cohort))
        existing = int(
            await conn.scalar(select(func.count()).select_from(attempts).where(cohort)) or 0
        )
    rng = case_rng(seed, slug)
    plays = [simulate_attempt(key.case, rng) for _ in range(n)]  # same sequence on every run
    for attempt in plays[existing:]:
        await record_attempt(conn, key, attempt, simulated_label=COHORT_LABEL)
    return max(0, n - existing)


async def run(*, n: int, seed: int, slugs: list[str], reset: bool) -> int:
    engine = make_engine(get_settings().sqlalchemy_url)
    missing = 0
    try:
        async with engine.connect() as conn:
            for slug in slugs:
                try:
                    added = await simulate_case(conn, slug, n=n, seed=seed, reset=reset)
                except LookupError as exc:
                    missing += 1
                    print(f"missing  {exc}")
                    continue
                print(f"{'added' if added else 'kept':8} {slug} ({added} new simulated attempts)")
    finally:
        await engine.dispose()
    return 1 if missing else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Insert a simulated cohort per showcase case.")
    parser.add_argument("--n", type=int, default=200)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--slug", action="append", dest="slugs", help="repeatable; default: seeds")
    parser.add_argument("--reset", action="store_true", help="delete and rebuild the cohorts")
    args = parser.parse_args(argv)
    slugs = args.slugs or seed_slugs()
    return asyncio.run(run(n=args.n, seed=args.seed, slugs=slugs, reset=args.reset))


if __name__ == "__main__":
    sys.exit(main())
