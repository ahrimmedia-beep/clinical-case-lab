"""Model price table and allowlist, loaded from pricing.yaml (one place to update)."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

PRICING_FILE = Path(__file__).with_name("pricing.yaml")


@dataclass(frozen=True)
class ModelPrice:
    provider: str
    model: str
    input_per_mtok: float
    output_per_mtok: float
    default: bool


@lru_cache(maxsize=4)
def load_pricing(path: Path = PRICING_FILE) -> dict[str, ModelPrice]:
    """Return prices keyed by "provider/model"."""
    raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    table: dict[str, ModelPrice] = {}
    for row in raw["models"]:
        price = ModelPrice(
            provider=str(row["provider"]),
            model=str(row["model"]),
            input_per_mtok=float(row["input"]),
            output_per_mtok=float(row["output"]),
            default=bool(row.get("default", False)),
        )
        table[f"{price.provider}/{price.model}"] = price
    return table


def allowed_models(provider: str) -> list[str]:
    return [p.model for p in load_pricing().values() if p.provider == provider]


def default_model(provider: str) -> str:
    for price in load_pricing().values():
        if price.provider == provider and price.default:
            return price.model
    raise KeyError(f"no default model for provider {provider!r} in pricing.yaml")


def cost_usd(provider: str, model: str, input_tokens: int, output_tokens: int) -> float:
    """Cost of one call; 0.0 for models without a price (the fake provider)."""
    price = load_pricing().get(f"{provider}/{model}")
    if price is None:
        return 0.0
    total = input_tokens * price.input_per_mtok + output_tokens * price.output_per_mtok
    return round(total / 1_000_000, 6)
