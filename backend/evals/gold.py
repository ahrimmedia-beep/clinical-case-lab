"""Gold set loader: evals/gold/<id>.txt (case report) + <id>.json (labels), listed in the manifest.

Eight cases and no dev/test split (spec §11): every case is scored and reported.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from pipeline.models import ExtractedFacts

GOLD_DIR = Path(__file__).parent / "gold"
Trap = Literal[
    "negation", "abbreviation", "unit_variant", "distractor_history", "number_in_words", "phi"
]


class GoldCase(BaseModel):
    """Labels for one case: ExtractedFacts plus what the matchers need."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    facts: ExtractedFacts
    diagnosis_aliases: list[str] = Field(default_factory=list)
    measurement_aliases: dict[str, list[str]] = Field(default_factory=dict)  # gold name -> aliases
    negated: list[str] = Field(default_factory=list)  # denied in the text; never a finding
    traps: list[Trap] = Field(default_factory=list)


class ManifestEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    diagnosis: str


@dataclass(frozen=True)
class GoldItem:
    case_id: str
    text: str
    gold: GoldCase


def load_manifest(gold_dir: Path = GOLD_DIR) -> list[ManifestEntry]:
    raw: dict[str, Any] = yaml.safe_load((gold_dir / "manifest.yaml").read_text(encoding="utf-8"))
    return [ManifestEntry.model_validate(row) for row in raw["cases"]]


def load_gold(gold_dir: Path = GOLD_DIR) -> list[GoldItem]:
    """Every gold case, in manifest order."""
    items: list[GoldItem] = []
    for entry in load_manifest(gold_dir):
        text = (gold_dir / f"{entry.id}.txt").read_text(encoding="utf-8")
        gold = GoldCase.model_validate_json((gold_dir / f"{entry.id}.json").read_text("utf-8"))
        items.append(GoldItem(case_id=entry.id, text=text, gold=gold))
    return items
