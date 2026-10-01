"""Helpers shared by the Postgres-backed tests."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://caselab:caselab@localhost:5434/caselab_test"
)
TABLES = (
    "attempt_choices, attempts, decision_accepted_answers, decision_options, case_decisions, "
    "case_diagnoses, case_measurements, case_findings, cases"
)
ALEMBIC = str(Path(sys.executable).parent / "alembic")


def run_alembic(*args: str) -> subprocess.CompletedProcess[str]:
    """Run the real Alembic CLI against the test database (same path as CI and Cloud Run)."""
    env = {**os.environ, "DATABASE_URL": TEST_DATABASE_URL}
    env.pop("CLOUD_SQL_INSTANCE", None)
    result = subprocess.run(
        [ALEMBIC, *args], cwd=BACKEND, env=env, capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise AssertionError(f"alembic {' '.join(args)} failed:\n{result.stdout}\n{result.stderr}")
    return result
