"""Write openapi.json and the case JSON Schema. Run: `uv run python -m app.export_schemas`."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.main import create_app
from app.schemas.case import ClinicalCase

REPO = Path(__file__).resolve().parents[2]


def _dump(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def main() -> None:
    _dump(REPO / "backend" / "openapi.json", create_app().openapi())
    case_schema = ClinicalCase.model_json_schema()
    case_schema["$id"] = (
        "https://github.com/ahrimmedia-beep/clinical-case-lab/schemas/clinical-case.schema.json"
    )
    _dump(REPO / "schemas" / "clinical-case.schema.json", case_schema)


if __name__ == "__main__":
    main()
