"""Text normalization shared by validators, scoring, spoiler redaction and grounding."""

from __future__ import annotations

import re
import unicodedata

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize(text: str) -> str:
    # Drop accents only; any other non-ASCII character (curly quotes, dashes) becomes a separator.
    decomposed = unicodedata.normalize("NFKD", text)
    unaccented = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return _NON_ALNUM.sub(" ", unaccented.lower()).strip()


def contains_term(haystack: str, term: str) -> bool:
    needle = normalize(term)
    if not needle:
        return False
    return f" {needle} " in f" {normalize(haystack)} "
