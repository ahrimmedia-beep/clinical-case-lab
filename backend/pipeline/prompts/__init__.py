"""Versioned prompts. Bump PROMPT_VERSION (and add *_v2.md) whenever a prompt changes:
eval caches and recordings are keyed by it, so old results are never mixed with new ones."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

PROMPT_VERSION = "v1"
_DIR = Path(__file__).parent


def load_prompt(name: Literal["extract", "author"], version: str = PROMPT_VERSION) -> str:
    return (_DIR / f"{name}_{version}.md").read_text(encoding="utf-8")


def with_repair(user: str, errors: str) -> str:
    """Append validator feedback to the original user message for a re-ask."""
    return (
        f"{user}\n\nYour previous answer was rejected by the validator:\n"
        f"<validation_errors>\n{errors}\n</validation_errors>\n"
        "Return a corrected, complete JSON object that fixes every error."
    )
