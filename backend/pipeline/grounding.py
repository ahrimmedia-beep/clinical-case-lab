"""Verbatim grounding: find each evidence quote in the source and return its offsets.

Ported from the job radar's `verify_evidence` (whitespace/case-normalized containment), extended
with offsets into the ORIGINAL text and a strict fuzzy fallback for small transcription slips.

1. Normalize both strings the same way (collapse whitespace, curly -> straight quotes, unicode
   dashes -> "-", lowercase) while keeping a map from normalized to original positions.
2. Exact substring search on the normalized text.
3. Fallback: rapidfuzz `partial_ratio_alignment` >= 92 on a window of nearly the quote's length.
Quotes shorter than 8 characters are never grounded: they would match almost anywhere.
"""

from __future__ import annotations

from functools import lru_cache

from rapidfuzz import fuzz

from app.schemas.extract import EvidenceSpan
from pipeline.models import ExtractedFacts

MIN_QUOTE_CHARS = 8
FUZZY_THRESHOLD = 92.0
MAX_EVIDENCE_CHARS = 600  # same limit as Finding/Measurement/Diagnosis.evidence

# curly quotes and primes -> straight quotes, unicode dashes -> "-", ellipsis -> "..."
_CHAR_MAP = str.maketrans(
    {
        "\u2018": "'", "\u2019": "'", "\u201a": "'", "\u201b": "'", "\u2032": "'",
        "\u201c": '"', "\u201d": '"', "\u201e": '"', "\u2033": '"',
        "\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-", "\u2014": "-",
        "\u2212": "-", "\u2026": "...",
    }
)  # fmt: skip
_QUOTES = "\"'\u201c\u201d\u2018\u2019\u00ab\u00bb"
_TRAILING = ".,;:"


@lru_cache(maxsize=32)
def _normalize_with_map(text: str) -> tuple[str, tuple[int, ...]]:
    """Return (normalized text, original index of every normalized character)."""
    chars: list[str] = []
    index: list[int] = []
    pending_space = False
    for i, ch in enumerate(text):
        if ch.isspace():
            pending_space = bool(chars)
            continue
        if pending_space:
            chars.append(" ")
            index.append(i - 1)
            pending_space = False
        for out in ch.translate(_CHAR_MAP).lower():
            chars.append(out)
            index.append(i)
    return "".join(chars), tuple(index)


def _clean_quote(quote: str) -> str:
    """Drop whitespace, quotes that wrap the whole quote, and trailing punctuation."""
    text = quote.strip()
    for _ in range(2):
        while len(text) >= 2 and text[0] in _QUOTES and text[-1] in _QUOTES:
            text = text[1:-1].strip()
        text = text.rstrip(_TRAILING).strip()
    return text


def _refine(needle: str, haystack: str, start: int, end: int) -> tuple[int, int]:
    """Nudge a fuzzy window's edges to the best full-string ratio (fixes off-by-a-few ends)."""
    slack = min(12, max(2, len(needle) // 10))
    best = (fuzz.ratio(needle, haystack[start:end]), start, end)
    for s in range(max(0, start - slack), min(len(haystack), start + slack) + 1):
        for e in range(max(s + 1, end - slack), min(len(haystack), end + slack) + 1):
            score = fuzz.ratio(needle, haystack[s:e])
            if score > best[0]:
                best = (score, s, e)
    return best[1], best[2]


def locate(quote: str, source: str) -> tuple[int, int] | None:
    """Offsets (start, end) of `quote` in `source` such that source[start:end] is the match."""
    needle, _ = _normalize_with_map(_clean_quote(quote))
    if len(needle) < MIN_QUOTE_CHARS:
        return None
    haystack, index = _normalize_with_map(source)
    if len(needle) > len(haystack):
        return None
    pos = haystack.find(needle)
    if pos >= 0:
        return index[pos], index[pos + len(needle) - 1] + 1
    hit = fuzz.partial_ratio_alignment(needle, haystack, score_cutoff=FUZZY_THRESHOLD)
    if hit is None:
        return None
    start, end = _refine(needle, haystack, hit.dest_start, hit.dest_end)
    if not 0.8 * len(needle) <= end - start <= 1.25 * len(needle):
        return None
    while start < end and haystack[start] == " ":
        start += 1
    while end > start and haystack[end - 1] == " ":
        end -= 1
    if end <= start:
        return None
    return index[start], index[end - 1] + 1


def ground_facts(
    facts: ExtractedFacts, source: str
) -> tuple[ExtractedFacts, list[EvidenceSpan], list[str]]:
    """Locate every evidence quote. Grounded quotes are replaced by the exact source slice.

    Returns the updated facts, one span per item (paths like "findings[3]") and warnings.
    """
    spans: list[EvidenceSpan] = []
    warnings: list[str] = []

    def check(path: str, evidence: str | None) -> str | None:
        quote = (evidence or "").strip()
        hit = locate(quote, source) if quote else None
        if hit is None or hit[1] - hit[0] > MAX_EVIDENCE_CHARS:
            spans.append(EvidenceSpan(path=path, quote=quote, start=None, end=None, grounded=False))
            reason = "evidence not found in the source text" if quote else "no evidence quote"
            warnings.append(f"{path}: {reason}")
            return evidence
        start, end = hit
        verbatim = source[start:end]
        spans.append(EvidenceSpan(path=path, quote=verbatim, start=start, end=end, grounded=True))
        return verbatim

    findings = [
        f.model_copy(update={"evidence": check(f"findings[{i}]", f.evidence)})
        for i, f in enumerate(facts.findings)
    ]
    measurements = [
        m.model_copy(update={"evidence": check(f"measurements[{i}]", m.evidence)})
        for i, m in enumerate(facts.measurements)
    ]
    final = facts.final_diagnosis.model_copy(
        update={"evidence": check("final_diagnosis", facts.final_diagnosis.evidence)}
    )
    differential = [
        d.model_copy(update={"evidence": check(f"differential[{i}]", d.evidence)})
        for i, d in enumerate(facts.differential)
    ]
    grounded = facts.model_copy(
        update={
            "findings": findings,
            "measurements": measurements,
            "final_diagnosis": final,
            "differential": differential,
        }
    )
    return grounded, spans, warnings


def grounded_ratio(spans: list[EvidenceSpan]) -> float:
    if not spans:
        return 1.0
    return round(sum(1 for s in spans if s.grounded) / len(spans), 4)
