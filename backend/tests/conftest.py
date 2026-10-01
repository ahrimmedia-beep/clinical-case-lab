"""Shared fixtures. Tests must never call a paid API."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.config import get_settings

FIXTURES = Path(__file__).parent / "fixtures"

PAID_KEYS = (
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "GCP_PROJECT",
    "GOOGLE_CLOUD_PROJECT",
)


@pytest.fixture(autouse=True)
def no_paid_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in PAID_KEYS:
        monkeypatch.delenv(key, raising=False)
    get_settings.cache_clear()


def load_fixture(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((FIXTURES / name).read_text())
    return data


@pytest.fixture
def case_pe() -> dict[str, Any]:
    return load_fixture("case_pe.json")
