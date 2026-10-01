"""Pure scoring (spec §9). No I/O: the attempts endpoint, the cohort simulator and the AI
players all go through `score_attempt`.

Points come only from the diagnosis (1) and the treatment plan. Every other decision is marked
right / wrong / missed without points, like Eximion's debrief. Two anti-gaming rules:

* treatment points = max(0, right - wrong), and any harmful treatment pick zeroes them, so
  ticking every option scores nothing;
* a diagnosis that names several candidates ("PE or pneumonia", "PE, pneumothorax",
  "PE pneumothorax") is wrong (`hedged`), while one diagnosis named more specifically
  ("sporadic LAM with recurrent pneumothorax", "Acute PE, provoked") is right.
"""

from __future__ import annotations

import itertools
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from rapidfuzz import fuzz

from app.schemas.attempt import AttemptIn, Calibration, MultiSelectStage, OptionState
from app.schemas.case import ClinicalCase, Decision
from app.stages import DecisionStage, Stage
from app.textnorm import normalize

FUZZY_THRESHOLD = 90

ABBREVIATIONS: dict[str, str] = {
    "pe": "pulmonary embolism",
    "lam": "lymphangioleiomyomatosis",
    "aatd": "alpha 1 antitrypsin deficiency",
    "a1atd": "alpha 1 antitrypsin deficiency",
    "a1at": "alpha 1 antitrypsin",
    "copd": "chronic obstructive pulmonary disease",
    "ipf": "idiopathic pulmonary fibrosis",
    "cap": "community acquired pneumonia",
    "abpa": "allergic bronchopulmonary aspergillosis",
    "pap": "pulmonary alveolar proteinosis",
    "dvt": "deep vein thrombosis",
    "ptx": "pneumothorax",
    "tb": "tuberculosis",
    "mi": "myocardial infarction",
    "chf": "congestive heart failure",
    "gerd": "gastro oesophageal reflux disease",
    "gord": "gastro oesophageal reflux disease",
    "bhd": "birt hogg dube syndrome",
    "plch": "pulmonary langerhans cell histiocytosis",
}

# Severity / course words that do not change the diagnosis ("acute PE" is PE). They are dropped
# from both sides before fuzzy matching; equality checks still see the full text.
QUALIFIERS: frozenset[str] = frozenset(
    {"acute", "subacute", "chronic", "massive", "submassive", "bilateral", "sporadic"}
)

# Explicit hedge markers (spec §9): " or ", " vs ", " vs. ", " versus ", "/", "|", ";",
# "and/or", "?". Any of them in the raw text makes the answer a hedge.
_EXPLICIT_HEDGE = re.compile(r"\bor\b|\bvs\b|\bversus\b|[/|;?]", re.IGNORECASE)
# Every separator: the markers above, commas, line breaks and spaced dashes (" - ", " -- ",
# " – ", " — "; a hyphen inside a name such as "Birt-Hogg-Dube" is not one). These split an
# answer into its parts; "and" / "&" / "+" / "plus" split a part further (`_list_items`).
_HEDGE_SPLIT = re.compile(
    r"\band/or\b|\bor\b|\bversus\b|\bvs\b\.?|[,/|;?\r\n]|\s+(?:-{1,2}|[–—])\s+", re.IGNORECASE
)

# From one of these words on, a part qualifies the diagnosis before it ("Acute PE, secondary to
# DVT", "LAM with recurrent pneumothorax and renal angiomyolipoma"); it names no new candidate.
_CONNECTORS: frozenset[str] = frozenset(
    {
        "with",
        "without",
        "no",
        "not",
        "secondary",
        "due",
        "caused",
        "causing",
        "complicated",
        "complicating",
        "associated",
        "presenting",
        "provoked",
        "triggered",
        "related",
        "following",
        "after",
        "from",
        "in",
        "on",
    }
)
# Inside a part, these join list items ("PE and pneumothorax", "PE + pneumothorax"), but only
# before the first connector ("LAM with pneumothorax and renal angiomyolipoma" is one diagnosis).
_CONJUNCTIONS: frozenset[str] = frozenset({"and", "plus"})
# Softeners are ignored in a list item: "PE, likely pneumothorax" still lists two candidates.
_SOFTENERS: frozenset[str] = frozenset(
    {"likely", "probable", "probably", "possible", "possibly", "suspected", "presumed"}
)

# A negation before the diagnosis ("not PE", "no evidence of PE") or right after it ("PE ruled
# out") means the answer does not name it. "PE without right heart strain" still names PE.
_NEGATION_BEFORE = re.compile(
    r"\b(?:no|not|without|exclud\w*|rule[ds]? out|negative for|absence of|free of)\b"
)
_NEGATION_AFTER = re.compile(r"^(?:\w+ ){0,2}(?:excluded|unlikely|ruled out)\b")

# Key shared by every accepted name of the case's own diagnosis.
_ANSWER = ""
# A last word that a vocabulary name can drop: "Birt-Hogg-Dube" names "Birt-Hogg-Dube syndrome".
_GENERIC_LAST_WORDS: frozenset[str] = frozenset({"syndrome", "disease", "disorder"})


@dataclass(frozen=True)
class OptionMark:
    key: str
    chosen: bool
    state: OptionState
    is_harmful: bool


@dataclass(frozen=True)
class StageScore:
    stage: Stage
    right: int
    wrong: int
    missed: int
    harmful: int
    points: int
    max_points: int
    options: tuple[OptionMark, ...] = ()


@dataclass(frozen=True)
class DiagnosisScore:
    text: str
    answered: bool
    correct: bool
    confidence: int
    calibration: Calibration
    hedged: bool = False


@dataclass(frozen=True)
class AttemptScore:
    stages: dict[Stage, StageScore]
    diagnosis: DiagnosisScore
    points: int
    max_points: int
    right: int
    wrong: int
    missed: int
    harmful: int
    total_decisions: int


def _collapse_initials(tokens: list[str]) -> list[str]:
    """Join runs of single letters: "p e" (from "P.E.") becomes "pe"."""
    out: list[str] = []
    run: list[str] = []
    for token in [*tokens, ""]:
        if len(token) == 1 and token.isalpha():
            run.append(token)
            continue
        if run:
            out.append("".join(run))
            run = []
        if token:
            out.append(token)
    return out


def _diagnosis_tokens(text: str) -> list[str]:
    """Normalized words with dotted initials collapsed and abbreviations expanded."""
    tokens = _collapse_initials(normalize(text).split())
    return " ".join(ABBREVIATIONS.get(token, token) for token in tokens).split()


def normalize_diagnosis(text: str) -> str:
    """Normalize, collapse dotted initials, expand abbreviations, drop repeated tokens.

    "Pulmonary embolism (PE)" and "pulmonary embolism" both become "pulmonary embolism".
    """
    return " ".join(dict.fromkeys(_diagnosis_tokens(text)))


def _without_qualifiers(normalized: str) -> str:
    kept = [t for t in normalized.split() if t not in QUALIFIERS]
    return " ".join(kept) or normalized


def diagnosis_candidates(text: str) -> list[str]:
    """Split free text on every separator (the explicit hedge markers, commas, line breaks and
    spaced dashes); blank parts are dropped."""
    return [part.strip() for part in _HEDGE_SPLIT.split(text) if normalize(part)]


def diagnosis_matches(answer: str, accepted: Sequence[str]) -> bool:
    """One candidate against the accepted answers: equal after normalization, or
    `token_sort_ratio >= 90` (not `token_set_ratio`, which scores any superset 100)."""
    given = normalize_diagnosis(answer)
    if not given:
        return False
    given_core = _without_qualifiers(given)
    for candidate in accepted:
        target = normalize_diagnosis(candidate)
        if not target:
            continue
        if given == target:
            return True
        if fuzz.token_sort_ratio(given_core, _without_qualifiers(target)) >= FUZZY_THRESHOLD:
            return True
    return False


def _phrase_spans(tokens: list[str], phrase: list[str], *, fuzzy: bool) -> list[tuple[int, int]]:
    """Where `phrase` occurs in `tokens` as whole words. With `fuzzy`, a window of the same
    length with `ratio >= 90` also counts ("pulmonary emboli" for "pulmonary embolism")."""
    n = len(phrase)
    if not n:
        return []
    target = " ".join(phrase)
    spans: list[tuple[int, int]] = []
    for start in range(len(tokens) - n + 1):
        window = tokens[start : start + n]
        if window == phrase or (fuzzy and fuzz.ratio(" ".join(window), target) >= FUZZY_THRESHOLD):
            spans.append((start, start + n))
    return spans


def _negated(before: list[str], after: list[str]) -> bool:
    return bool(_NEGATION_BEFORE.search(" ".join(before)) or _NEGATION_AFTER.match(" ".join(after)))


def names_accepted_answer(text: str, accepted: Sequence[str]) -> bool:
    """True if the text names an accepted answer: near-equal to it (`diagnosis_matches`), or
    containing it as a whole phrase with extra qualifiers ("AATD-related panlobular emphysema",
    "acute PE secondary to DVT"). A negated mention ("not PE", "PE ruled out") does not count.
    A negation before the name reaches only inside its own part ("not pneumothorax, PE" names
    PE); a cue right after it may follow a separator ("PE, ruled out").
    """
    tokens = _diagnosis_tokens(text)
    # A trailing cue ("PE excluded") never passes the near-equal check, so only leading ones.
    if diagnosis_matches(text, accepted) and not _NEGATION_BEFORE.search(" ".join(tokens)):
        return True
    parts = [_diagnosis_tokens(part) for part in diagnosis_candidates(text)]
    for i, part in enumerate(parts):
        following = [token for later in parts[i + 1 :] for token in later]
        for answer in accepted:
            for start, end in _phrase_spans(part, _diagnosis_tokens(answer), fuzzy=True):
                if not _negated(part[:start], [*part[end:], *following]):
                    return True
    return False


def diagnosis_vocabulary(case: ClinicalCase) -> list[str]:
    """Every diagnosis the case names: its accepted answers and final diagnosis, the
    differential, and the options of the differential decision (duplicates dropped)."""
    terms = [*case.diagnosis_terms(), *(d.name for d in case.differential)]
    for decision in case.decisions:
        if decision.stage == DecisionStage.DIFFERENTIAL:
            terms.extend(o.text for o in decision.options)
    seen: set[str] = set()
    unique: list[str] = []
    for term in terms:
        key = normalize(term)
        if key and key not in seen:
            seen.add(key)
            unique.append(term)
    return unique


def _list_items(text: str) -> list[list[str]]:
    """The candidate items of an answer, as diagnosis tokens: each part (`diagnosis_candidates`)
    up to its first connector word, split on "and" / "&" / "+" / "plus". A part that opens with
    a connector yields none.
    """
    items: list[list[str]] = []
    for part in diagnosis_candidates(text):
        spaced = part.replace("&", " and ").replace("+", " and ")
        tokens = [t for t in _diagnosis_tokens(spaced) if t not in _SOFTENERS]
        item: list[str] = []
        for token in [*tokens, "and"]:
            if token in _CONNECTORS:
                break
            if token in _CONJUNCTIONS:
                if item:
                    items.append(item)
                item = []
            else:
                item.append(token)
        if item:
            items.append(item)
    return items


@dataclass(frozen=True)
class _Term:
    """One vocabulary diagnosis: its text, the token phrases that name it, and its key."""

    text: str
    phrases: tuple[tuple[str, ...], ...]
    key: str


def _term(text: str, key: str) -> _Term:
    """The phrases are the full name, its head before the first connector ("COPD from smoking
    alone" -> "COPD") and that head without a generic last word when two or more words remain
    ("Birt-Hogg-Dube syndrome" -> "Birt-Hogg-Dube")."""
    tokens = tuple(_diagnosis_tokens(text))
    head = tuple(itertools.takewhile(lambda t: t not in _CONNECTORS, tokens))
    phrases = [tokens]
    if head and head != tokens:
        phrases.append(head)
    if len(head) >= 3 and head[-1] in _GENERIC_LAST_WORDS:
        phrases.append(head[:-1])
    return _Term(text, tuple(phrases), key)


def _vocabulary_terms(accepted: Sequence[str], vocabulary: Sequence[str]) -> list[_Term]:
    accepted_keys = {normalize_diagnosis(a) for a in accepted}
    terms: list[_Term] = []
    for text in (*accepted, *vocabulary):
        key = normalize_diagnosis(text)
        if key:
            terms.append(_term(text, _ANSWER if key in accepted_keys else key))
    return terms


def _named_diagnoses(tokens: list[str], terms: Sequence[_Term]) -> set[str]:
    """Keys of the vocabulary diagnoses one list item names; empty if it only qualifies.

    An item names a term if it contains one of the term's phrases (whole phrase, or a
    near-equal window) or the term contains the item (whole phrase, item >= 4 characters).
    Every accepted name of the case's diagnosis shares one key.
    """
    if all(t in QUALIFIERS for t in tokens):
        return set()
    text = " ".join(tokens)
    return {
        term.key
        for term in terms
        if any(_phrase_spans(tokens, list(p), fuzzy=True) for p in term.phrases)
        or diagnosis_matches(text, [term.text])
        or (len(text) >= 4 and _phrase_spans(list(term.phrases[0]), tokens, fuzzy=False))
    }


def _names_two_diagnoses(tokens: list[str], terms: Sequence[_Term]) -> bool:
    """True if one list item names two different vocabulary diagnoses side by side, with no
    connector between them ("PE pneumothorax", "LAM BHD"). A name inside a longer one
    ("pneumothorax" in "primary spontaneous pneumothorax") is part of it, not a second name."""
    found = {
        (start, end, term.key)
        for term in terms
        for phrase in term.phrases
        for start, end in _phrase_spans(tokens, list(phrase), fuzzy=True)
    }
    widest = [
        (s, e, k)
        for s, e, k in found
        if not any(s2 <= s and e <= e2 and e2 - s2 > e - s for s2, e2, _ in found)
    ]
    return any(
        k1 != k2 and (e1 <= s2 or e2 <= s1)
        for (s1, e1, k1), (s2, e2, k2) in itertools.combinations(widest, 2)
    )


def _is_listed_hedge(text: str, accepted: Sequence[str], vocabulary: Sequence[str]) -> bool:
    """Two or more list items that each name a diagnosis of the case vocabulary, with no
    diagnosis that all of them name ("PE, pneumothorax", "LAM and Birt-Hogg-Dube syndrome"),
    or one item that names two of them with no connector between ("PE pneumothorax")."""
    terms = _vocabulary_terms(accepted, vocabulary)
    items = _list_items(text)
    if any(_names_two_diagnoses(item, terms) for item in items):
        return True
    named = [keys for item in items if (keys := _named_diagnoses(item, terms))]
    return len(named) >= 2 and not set.intersection(*named)


def _squash(text: str) -> str:
    return " ".join(text.casefold().split())


def judge_diagnosis(
    text: str, accepted: Sequence[str], vocabulary: Sequence[str] = ()
) -> tuple[bool, bool]:
    """Return `(correct, hedged)` for a free-text diagnosis (spec §9).

    1. Blank -> `(False, False)` (missed).
    2. An explicit hedge marker (or / vs / versus / "/" / "|" / ";" / "?") -> hedged, unless
       the text is an accepted answer as written.
    3. A list (commas, spaced dashes, line breaks, or "and" / "&" / "+" / "plus" before any
       connector word such as "with") whose items name different diagnoses of the case
       vocabulary ("PE, pneumonia, COPD exacerbation", "PE - pneumothorax") -> hedged; so is
       one item naming two of them with no connector between ("PE pneumothorax", "LAM BHD").
       `vocabulary` is `diagnosis_vocabulary(case)`; a comma followed by qualifiers
       ("Sarcoidosis, Scadding stage II", "Acute PE, provoked") is not a list.
    4. Otherwise correct if it names an accepted answer (`names_accepted_answer`); a less
       specific answer ("Pneumothorax" for "Tension pneumothorax") is wrong.
    """
    given = normalize_diagnosis(text)
    if not given:
        return False, False
    if _squash(text) in {_squash(a) for a in accepted}:
        return True, False
    if _EXPLICIT_HEDGE.search(text):
        return False, True
    if any(given == normalize_diagnosis(a) for a in accepted):
        return True, False
    if _is_listed_hedge(text, accepted, vocabulary):
        return False, True
    return names_accepted_answer(text, accepted), False


def calibrate(confidence: int, correct: bool) -> Calibration:
    if confidence >= 4 and not correct:
        return Calibration.OVERCONFIDENT
    if confidence <= 2 and correct:
        return Calibration.UNDERCONFIDENT
    return Calibration.CALIBRATED


def score_multi_select(decision: Decision, chosen: Iterable[str]) -> StageScore:
    picked = set(chosen)
    stage = Stage(decision.stage)
    right = wrong = missed = harmful = 0
    marks: list[OptionMark] = []
    for option in decision.options:
        is_chosen = option.key in picked
        if is_chosen and option.is_correct:
            state = OptionState.RIGHT
            right += 1
        elif is_chosen:
            state = OptionState.WRONG
            wrong += 1
        elif option.is_correct:
            state = OptionState.MISSED
            missed += 1
        else:
            state = OptionState.NEUTRAL
        if is_chosen and option.is_harmful:
            harmful += 1
        marks.append(OptionMark(option.key, is_chosen, state, option.is_harmful))
    scored = stage is Stage.TREATMENT
    # Anti-gaming: wrong picks cancel right ones, and one harmful pick zeroes the plan.
    points = 0 if harmful else max(0, right - wrong)
    return StageScore(
        stage=stage,
        right=right,
        wrong=wrong,
        missed=missed,
        harmful=harmful,
        points=points if scored else 0,
        max_points=sum(1 for o in decision.options if o.is_correct) if scored else 0,
        options=tuple(marks),
    )


def unknown_choices(
    case: ClinicalCase, choices: Mapping[MultiSelectStage, Sequence[str]]
) -> list[str]:
    by_stage = {Stage(d.stage): d for d in case.decisions}
    problems: list[str] = []
    for stage_key, keys in choices.items():
        decision = by_stage.get(Stage(stage_key))
        if decision is None:
            problems.append(f"stage '{stage_key}' is not part of this case")
            continue
        valid = {o.key for o in decision.options}
        for key in sorted(set(keys) - valid):
            problems.append(f"option '{key}' does not exist in stage '{stage_key}'")
    return problems


def score_attempt(case: ClinicalCase, attempt: AttemptIn) -> AttemptScore:
    chosen = {Stage(k): v for k, v in attempt.choices.items()}
    scores: dict[Stage, StageScore] = {}
    for decision in case.decisions:
        stage = Stage(decision.stage)
        if stage is not Stage.DIAGNOSIS:
            scores[stage] = score_multi_select(decision, chosen.get(stage, []))

    answered = bool(normalize(attempt.diagnosis_text))
    correct, hedged = judge_diagnosis(
        attempt.diagnosis_text, case.diagnosis_terms(), diagnosis_vocabulary(case)
    )
    diagnosis = DiagnosisScore(
        text=attempt.diagnosis_text,
        answered=answered,
        correct=correct,
        confidence=attempt.confidence,
        calibration=calibrate(attempt.confidence, correct),
        hedged=hedged,
    )
    scores[Stage.DIAGNOSIS] = StageScore(
        stage=Stage.DIAGNOSIS,
        right=int(correct),
        wrong=int(answered and not correct),
        missed=int(not answered),
        harmful=0,
        points=int(correct),
        max_points=1,
    )
    ordered = {stage: scores[stage] for stage in Stage if stage in scores}
    parts = ordered.values()
    return AttemptScore(
        stages=ordered,
        diagnosis=diagnosis,
        points=sum(s.points for s in parts),
        max_points=sum(s.max_points for s in parts),
        right=sum(s.right for s in parts),
        wrong=sum(s.wrong for s in parts),
        missed=sum(s.missed for s in parts),
        harmful=sum(s.harmful for s in parts),
        total_decisions=1
        + sum(
            1
            for d in case.decisions
            if d.stage != DecisionStage.DIAGNOSIS
            for o in d.options
            if o.is_correct
        ),
    )
