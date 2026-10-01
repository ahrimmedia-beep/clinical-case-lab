"""CI floor: every committed recording, re-scored offline, must stay above its floor."""

from __future__ import annotations

from pathlib import Path

import pytest

from evals.gold import load_gold
from evals.report import build_report
from evals.run import EVALS_DIR, read_records

RECORDINGS = sorted((EVALS_DIR / "recordings").glob("*.jsonl"))
FAKE_FLOOR = 0.90  # the fake drops one finding per case and invents one on every third
LIVE_FLOOR = 0.60  # after the first live run: set to (lowest live macro-F1 - 0.10), never lower


def test_fake_recording_is_committed() -> None:
    assert EVALS_DIR / "recordings" / "fake__fake-gold__v1.jsonl" in RECORDINGS


@pytest.mark.parametrize("path", RECORDINGS, ids=lambda p: p.name)
def test_recording_covers_every_gold_case(path: Path) -> None:
    assert {r.case_id for r in read_records(path).values()} >= {i.case_id for i in load_gold()}


@pytest.mark.parametrize("path", RECORDINGS, ids=lambda p: p.name)
def test_recording_meets_its_floor(path: Path) -> None:
    provider, model, prompt_version = path.stem.split("__")
    items = load_gold()
    wanted = {item.case_id for item in items}
    records = [r for r in read_records(path).values() if r.case_id in wanted]
    assert records, "recording has no case from the current gold set"
    report = build_report({(provider, model): records}, items, prompt_version=prompt_version)
    floor = FAKE_FLOOR if provider == "fake" else LIVE_FLOOR
    assert report.models[0].macro_f1 >= floor
