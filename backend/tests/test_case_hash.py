from __future__ import annotations

import copy
import json
import re
from typing import Any

from app.repository.cases import canonical_json, content_hash, make_slug
from app.schemas.case import ClinicalCase


def reorder(value: Any) -> Any:
    """Reverse the key order of every object, recursively."""
    if isinstance(value, dict):
        return {k: reorder(value[k]) for k in reversed(list(value))}
    if isinstance(value, list):
        return [reorder(v) for v in value]
    return value


def test_hash_ignores_key_order_whitespace_and_source(case_pe: dict[str, Any]) -> None:
    original = ClinicalCase.model_validate(case_pe)
    shuffled = reorder(copy.deepcopy(case_pe))
    shuffled["title"] = "   " + shuffled["title"] + "  "
    shuffled["source"] = {"kind": "llm", "provider": "gemini", "model": "m", "prompt_version": "v1"}
    again = ClinicalCase.model_validate(json.loads(json.dumps(shuffled, indent=4)))
    assert content_hash(again) == content_hash(original)
    assert len(content_hash(original)) == 64
    assert '"source"' not in canonical_json(original)


def test_hash_changes_when_content_changes(case_pe: dict[str, Any]) -> None:
    changed = copy.deepcopy(case_pe)
    changed["estimated_minutes"] = 6
    assert content_hash(ClinicalCase.model_validate(changed)) != content_hash(
        ClinicalCase.model_validate(case_pe)
    )


def test_slug_is_url_safe_and_bounded() -> None:
    digest = "abcdef0123456789" * 4
    assert make_slug("Sudden breathlessness after a long flight", digest) == (
        "sudden-breathlessness-after-a-long-flight-abcdef"
    )
    long_slug = make_slug("Très " * 60, digest)
    assert re.fullmatch(r"[a-z0-9-]{3,100}", long_slug)
    assert not long_slug.startswith("-") and "--" not in long_slug
    assert make_slug("???", digest) == "case-abcdef"
