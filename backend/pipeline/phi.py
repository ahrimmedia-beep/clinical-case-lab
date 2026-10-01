"""Regex de-identification of clinical text before any LLM call.

Covers a practical subset of the HIPAA Safe Harbor identifiers: names after titles or a
"Patient:/Name:" label, phone numbers, e-mail addresses, dates, MRN/account numbers, SSNs,
street addresses and ZIP codes. Each distinct value becomes a numbered placeholder such as
`[NAME_1]`; the caller gets the counts per label (never the values).

`assert_clean()` is the last guard before text leaves the process: it re-scans for the
high-precision patterns and raises if anything is left.

Production swap-in: Google Sensitive Data Protection (Cloud DLP) `deidentify` or Presidio
behind the same two functions.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from app.schemas.extract import PhiCount

_L = r"[^\W\d_]"  # any Unicode letter
_UPPER = r"[A-ZÀ-ÖØ-ÞĀ-ž]"  # Latin capitals incl. accented ones (Á, Ø, Ł, ...)
_NAME_TOKEN = rf"(?:{_UPPER}\.|{_UPPER}{_L}*(?:['’-]{_L}+)*)"
_NAME = rf"{_NAME_TOKEN}(?:[ \t]+{_NAME_TOKEN}){{0,2}}"
_MONTH = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?"
    r"|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
)
_STATES = frozenset(
    "AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH "
    "NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split()
)
_NOT_A_NAME = frozenset(
    "the a an this he she they patient pt is was has male female man woman unknown none n".split()
)


def _plausible_date(m: re.Match[str]) -> bool:
    first, second = int(m.group("a")), int(m.group("b"))
    return (first <= 12 and second <= 31) or (second <= 12 and first <= 31)


def _is_state(m: re.Match[str]) -> bool:
    return m.group("state") in _STATES


def _is_name(m: re.Match[str]) -> bool:
    return m.group("phi").split()[0].lower().rstrip(".") not in _NOT_A_NAME


@dataclass(frozen=True)
class _Rule:
    label: str
    pattern: re.Pattern[str]
    accept: Callable[[re.Match[str]], bool] | None = None
    guard: bool = True  # also checked by assert_clean()


_RULES: tuple[_Rule, ...] = (
    _Rule("EMAIL", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")),
    _Rule("SSN", re.compile(r"(?<![\d-])\d{3}-\d{2}-\d{4}(?![\d-])")),
    _Rule(
        "ID",
        re.compile(
            r"\b(?:MRN|MR#|medical record(?: number| no\.?)?|patient id|account(?: number| no\.?)?"
            r"|acct)\s*(?:#|no\.?|number)?\s*[:#]?\s*(?P<phi>(?=[A-Z0-9-]*\d)[A-Z0-9][A-Z0-9-]{3,})",
            re.IGNORECASE,
        ),
    ),
    _Rule(
        "PHONE",
        re.compile(
            r"(?<![\w-])(?:\+\d{1,3}[ .-]?)?(?:\(\d{3}\)[ ]?|\d{3}[ .-])\d{3}[ .-]\d{4}(?![\w-])"
        ),
    ),
    _Rule(
        "DATE",
        re.compile(
            r"(?<!\d)(?<!\d\.)(?P<a>\d{1,2})(?P<sep>[/.-])(?P<b>\d{1,2})(?P=sep)(?:\d{4}|\d{2})"
            r"(?!\d)(?!\.\d)"
        ),
        accept=_plausible_date,
    ),
    _Rule("DATE", re.compile(r"\b\d{4}-\d{2}-\d{2}\b")),
    _Rule(
        "DATE",
        re.compile(rf"\b{_MONTH}\.?[ \t]+\d{{1,2}}(?:st|nd|rd|th)?,?[ \t]+\d{{4}}\b"),
        guard=False,
    ),
    _Rule(
        "DATE",
        re.compile(rf"\b\d{{1,2}}(?:st|nd|rd|th)?[ \t]+{_MONTH}\.?,?[ \t]+\d{{4}}\b"),
        guard=False,
    ),
    _Rule("DATE", re.compile(rf"\b{_MONTH}[ \t]+\d{{4}}\b"), guard=False),
    _Rule(
        "ADDRESS",
        re.compile(
            r"\b\d{1,5}[ \t]+(?:[A-Z][\w'’.-]*[ \t]+){1,4}"
            r"(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Court|Ct|Way"
            r"|Place|Pl|Terrace|Ter|Parkway|Pkwy)\b\.?"
        ),
        guard=False,
    ),
    _Rule(
        "ZIP",
        re.compile(r"\b(?P<state>[A-Z]{2})[ \t]+(?P<phi>\d{5}(?:-\d{4})?)\b"),
        accept=_is_state,
        guard=False,
    ),
    _Rule(
        "NAME",
        re.compile(rf"\b(?:Patient|Name|Pt)[ \t]*:[ \t]*(?P<phi>{_NAME})"),
        accept=_is_name,
        guard=False,
    ),
    _Rule(
        "NAME",
        re.compile(rf"\b(?:Mr|Mrs|Ms|Miss|Mx|Dr|Prof)\.?[ \t]+(?P<phi>{_NAME})"),
        accept=_is_name,
        guard=False,
    ),
)
_LABEL_ORDER = ("NAME", "DATE", "PHONE", "EMAIL", "ID", "SSN", "ADDRESS", "ZIP")


class PhiLeakError(Exception):
    """Identifiers are still present after masking; the text must not be sent to a model."""

    def __init__(self, labels: list[str]) -> None:
        super().__init__(f"identifiers remain after masking: {', '.join(labels)}")
        self.labels = labels


def deidentify(text: str) -> tuple[str, list[PhiCount]]:
    """Mask identifiers. Same value -> same placeholder. Returns masked text and counts."""
    placeholders: dict[tuple[str, str], str] = {}
    next_index: dict[str, int] = {}
    counts: dict[str, int] = {}

    def placeholder(label: str, value: str) -> str:
        key = (label, value.casefold())
        if key not in placeholders:
            next_index[label] = next_index.get(label, 0) + 1
            placeholders[key] = f"[{label}_{next_index[label]}]"
        counts[label] = counts.get(label, 0) + 1
        return placeholders[key]

    masked = text
    for rule in _RULES:

        def replace(m: re.Match[str], rule: _Rule = rule) -> str:
            if rule.accept is not None and not rule.accept(m):
                return m.group(0)
            if "phi" in rule.pattern.groupindex:
                start, end = m.span("phi")
                whole_start = m.start()
                token = placeholder(rule.label, m.group("phi"))
                full = m.group(0)
                return full[: start - whole_start] + token + full[end - whole_start :]
            return placeholder(rule.label, m.group(0))

        masked = rule.pattern.sub(replace, masked)

    return masked, [
        PhiCount(label=label, count=counts[label]) for label in _LABEL_ORDER if label in counts
    ]


def assert_clean(text: str) -> None:
    """Raise PhiLeakError if a high-precision identifier pattern still matches."""
    found: list[str] = []
    for rule in _RULES:
        if not rule.guard or rule.label in found:
            continue
        for m in rule.pattern.finditer(text):
            if rule.accept is None or rule.accept(m):
                found.append(rule.label)
                break
    if found:
        raise PhiLeakError(found)
