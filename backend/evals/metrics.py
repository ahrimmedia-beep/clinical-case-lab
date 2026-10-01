"""Pure metric functions for the extraction eval (spec §11). No I/O, unit-tested.

Matching rules:
- findings: greedy one-to-one match on rapidfuzz token_sort_ratio >= 85 of the normalized texts
  (token_sort, not token_set: token_set scores "cough" vs "cough with blood-streaked sputum"
  as 100, so a finding that drops its key qualifier would count as found);
- measurements: name (or gold alias) match AND value within 2 % (or same text result) AND
  the same unit after unit normalization;
- final diagnosis: exact match with the name or an alias, token_sort_ratio >= 85, or the name
  named as a whole phrase with qualifiers; a hedge ("X or Y", "X vs Y", "X/Y") never counts
  (token_sort, not token_set: "pneumothorax" must not equal "tension pneumothorax");
- chief complaint: token_set_ratio >= 80 (a short complaint inside a longer one is fine);
- negation errors: an unmatched prediction with token_set_ratio >= 80 to a denied phrase.
No bootstrap confidence intervals: 8 synthetic cases is a smoke-level harness (spec §11).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from rapidfuzz import fuzz

from app.schemas.case import Measurement
from app.textnorm import contains_term, normalize

FINDING_MATCH = 85.0
NEGATION_MATCH = 80.0
CHIEF_COMPLAINT_MATCH = 80.0
DIAGNOSIS_MATCH = 85.0
NAME_MATCH = 90.0
VALUE_REL_TOL = 0.02


@dataclass(frozen=True)
class PRF:
    tp: int
    n_pred: int
    n_gold: int

    @property
    def precision(self) -> float:
        if self.n_pred == 0:
            return 1.0 if self.n_gold == 0 else 0.0
        return self.tp / self.n_pred

    @property
    def recall(self) -> float:
        if self.n_gold == 0:
            return 1.0 if self.n_pred == 0 else 0.0
        return self.tp / self.n_gold

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 0.0 if p + r == 0 else 2 * p * r / (p + r)

    def __add__(self, other: PRF) -> PRF:
        return PRF(self.tp + other.tp, self.n_pred + other.n_pred, self.n_gold + other.n_gold)


def text_similarity(a: str, b: str) -> float:
    """Lenient: a text contained in the other scores 100 (chief complaint, negations)."""
    return float(fuzz.token_set_ratio(normalize(a), normalize(b)))


def finding_similarity(a: str, b: str) -> float:
    """Strict but word-order-insensitive: qualifiers must be there on both sides."""
    return float(fuzz.token_sort_ratio(normalize(a), normalize(b)))


def greedy_pairs(
    n_pred: int, n_gold: int, score: Callable[[int, int], float], threshold: float
) -> list[tuple[int, int]]:
    """One-to-one (pred index, gold index) pairs with score >= threshold, best scores first."""
    scored = [
        (s, i, j) for i in range(n_pred) for j in range(n_gold) if (s := score(i, j)) >= threshold
    ]
    scored.sort(key=lambda t: (-t[0], t[1], t[2]))
    used_pred: set[int] = set()
    used_gold: set[int] = set()
    pairs: list[tuple[int, int]] = []
    for _, i, j in scored:
        if i not in used_pred and j not in used_gold:
            used_pred.add(i)
            used_gold.add(j)
            pairs.append((i, j))
    return sorted(pairs)


def match_findings(pred: Sequence[str], gold: Sequence[str]) -> list[tuple[int, int]]:
    return greedy_pairs(
        len(pred), len(gold), lambda i, j: finding_similarity(pred[i], gold[j]), FINDING_MATCH
    )


def exact(pred: object, gold: object) -> float:
    return 1.0 if pred == gold else 0.0


def chief_complaint_score(pred: str, gold: str) -> float:
    return 1.0 if text_similarity(pred, gold) >= CHIEF_COMPLAINT_MATCH else 0.0


_HEDGE = re.compile(r"\b(or|vs|versus)\b|/", re.IGNORECASE)


def diagnosis_correct(pred: str, gold: str, aliases: Sequence[str] = ()) -> bool:
    """Equal / near-equal to the name or an alias, or naming it as a whole phrase with extra
    qualifiers ("Sarcoidosis, Scadding stage II" for "Sarcoidosis"). A hedge naming several
    candidates ("X or Y", "X vs Y", "X/Y") never counts."""
    p = normalize(pred)
    if not p or _HEDGE.search(pred):
        return False
    for candidate in (gold, *aliases):
        c = normalize(candidate)
        if (
            p == c
            or fuzz.token_sort_ratio(p, c) >= DIAGNOSIS_MATCH
            or contains_term(pred, candidate)
        ):
            return True
    return False


_UNIT_SYNONYMS = {
    "bpm": "/min", "beats/min": "/min", "beatsperminute": "/min", "beats/minute": "/min",
    "breaths/min": "/min", "breathsperminute": "/min", "breaths/minute": "/min",
    "min-1": "/min", "/min": "/min", "/minute": "/min", "perminute": "/min",
    "°c": "c", "degc": "c", "celsius": "c", "c": "c",
    "%": "%", "percent": "%", "%predicted": "%", "%ofpredicted": "%", "%pred": "%",
    "x10^9/l": "10^9/l", "10^9/l": "10^9/l", "x10e9/l": "10^9/l", "10*9/l": "10^9/l",
    "/ul": "/ul", "cells/ul": "/ul", "/mm3": "/ul", "cells/mm3": "/ul",
    "mmhg": "mmhg",
}  # fmt: skip


def unit_key(unit: str | None) -> str:
    if not unit:
        return ""
    u = unit.strip().lower().replace("µ", "u").replace("μ", "u").replace("×", "x")
    u = u.replace("⁹", "^9").replace(" ", "")
    return _UNIT_SYNONYMS.get(u, u)


def _as_number(text: str | None) -> float | None:
    if not text:
        return None
    try:
        return float(text.replace(",", "").strip())
    except ValueError:
        return None


def value_matches(pred: Measurement, gold: Measurement) -> bool:
    if gold.value is not None:
        p = pred.value if pred.value is not None else _as_number(pred.value_text)
        if p is None:
            return False
        if gold.value == 0:
            return p == 0
        return abs(p - gold.value) <= VALUE_REL_TOL * abs(gold.value)
    gold_text = normalize(gold.value_text or "")
    pred_text = normalize(pred.value_text or (f"{pred.value:g}" if pred.value is not None else ""))
    if not gold_text or not pred_text:
        return False
    return gold_text == pred_text or fuzz.token_set_ratio(gold_text, pred_text) >= 90


def name_matches(pred_name: str, gold_name: str, aliases: Sequence[str] = ()) -> bool:
    p = normalize(pred_name)
    for candidate in (gold_name, *aliases):
        c = normalize(candidate)
        if p == c or fuzz.ratio(p, c) >= NAME_MATCH:
            return True
    return False


def match_measurements(
    pred: Sequence[Measurement],
    gold: Sequence[Measurement],
    aliases: Mapping[str, Sequence[str]] | None = None,
) -> list[tuple[int, int]]:
    known = aliases or {}

    def score(i: int, j: int) -> float:
        p, g = pred[i], gold[j]
        if not name_matches(p.name, g.name, known.get(g.name, ())):
            return 0.0
        if unit_key(p.unit) != unit_key(g.unit) or not value_matches(p, g):
            return 0.0
        return 1.0 + text_similarity(p.name, g.name)  # prefer the closer name

    return greedy_pairs(len(pred), len(gold), score, 1.0)


def negation_errors(
    pred_findings: Sequence[str], matched_pred: set[int], negated: Sequence[str]
) -> list[str]:
    """Predicted findings that match no gold finding but match something the text denies."""
    errors: list[str] = []
    for i, text in enumerate(pred_findings):
        if i in matched_pred:
            continue
        if any(text_similarity(text, phrase) >= NEGATION_MATCH for phrase in negated):
            errors.append(text)
    return errors


def percentile(values: Sequence[float], q: float) -> float:
    """Linear-interpolation percentile, q in [0, 100]."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = (len(ordered) - 1) * q / 100
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    return float(ordered[low] + (ordered[high] - ordered[low]) * (rank - low))


def rate(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0
