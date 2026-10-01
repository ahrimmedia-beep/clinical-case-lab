"""Hand-written SQL lives in app/db/sql/*.sql; this loads each file once per process."""

from __future__ import annotations

from functools import cache
from pathlib import Path

from sqlalchemy import TextClause, text

SQL_DIR = Path(__file__).parent / "sql"


@cache
def sql(name: str) -> TextClause:
    return text((SQL_DIR / f"{name}.sql").read_text(encoding="utf-8"))
