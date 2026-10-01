"""Tests for scripts/update_eval_tables.py.

The script lives at the repo root (outside backend/), since it edits README.md and
docs/EVALS.md, not backend code. It is loaded here by file path and exercised through its
public functions and its main() entry point, run by `make test-backend` like any other test.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "update_eval_tables.py"


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("update_eval_tables", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


uet = _load_module()

SAMPLE_REPORT = (
    "# Eval report\n\nintro\n\n| model | macro-F1 |\n|---|---|\n"
    "| gemini-3.8-flash | 0.91 |\n\nper-case details\n"
)
SAMPLE_TABLE = "| model | macro-F1 |\n|---|---|\n| gemini-3.8-flash | 0.91 |"


def test_first_table_extracts_only_the_table() -> None:
    assert uet.first_table(SAMPLE_REPORT) == SAMPLE_TABLE


def test_first_table_requires_a_data_row() -> None:
    with pytest.raises(ValueError, match="no Markdown table"):
        uet.first_table("# Eval report\n\nno table here\n")


def test_replace_between_markers_round_trip() -> None:
    text = "before\n<!-- eval-table:start -->\nold table\n<!-- eval-table:end -->\nafter\n"
    updated = uet.replace_between_markers(text, "new table")
    assert updated == (
        "before\n<!-- eval-table:start -->\nnew table\n<!-- eval-table:end -->\nafter\n"
    )


def test_replace_between_markers_missing_markers_raises() -> None:
    with pytest.raises(ValueError, match="markers"):
        uet.replace_between_markers("no markers here\n", "x")


def test_main_updates_the_target_and_is_idempotent(tmp_path: Path) -> None:
    report = tmp_path / "latest.md"
    report.write_text(SAMPLE_REPORT, encoding="utf-8")
    target = tmp_path / "README.md"
    target.write_text(
        "before\n<!-- eval-table:start -->\nold table\n<!-- eval-table:end -->\nafter\n",
        encoding="utf-8",
    )

    exit_code = uet.main(["--report", str(report), "--targets", str(target)])
    assert exit_code == 0
    updated = target.read_text(encoding="utf-8")
    assert updated == (
        f"before\n<!-- eval-table:start -->\n{SAMPLE_TABLE}\n<!-- eval-table:end -->\nafter\n"
    )

    # A second run over the same inputs changes nothing.
    exit_code = uet.main(["--report", str(report), "--targets", str(target)])
    assert exit_code == 0
    assert target.read_text(encoding="utf-8") == updated


def test_main_updates_multiple_targets(tmp_path: Path) -> None:
    report = tmp_path / "latest.md"
    report.write_text(SAMPLE_REPORT, encoding="utf-8")
    readme = tmp_path / "README.md"
    evals_doc = tmp_path / "EVALS.md"
    for target in (readme, evals_doc):
        target.write_text(
            "before\n<!-- eval-table:start -->\nold\n<!-- eval-table:end -->\nafter\n",
            encoding="utf-8",
        )

    exit_code = uet.main(["--report", str(report), "--targets", str(readme), str(evals_doc)])
    assert exit_code == 0
    for target in (readme, evals_doc):
        assert SAMPLE_TABLE in target.read_text(encoding="utf-8")


def test_main_fails_cleanly_when_markers_are_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report = tmp_path / "latest.md"
    report.write_text(SAMPLE_REPORT, encoding="utf-8")
    bad = tmp_path / "BAD.md"
    bad.write_text("no markers here\n", encoding="utf-8")

    exit_code = uet.main(["--report", str(report), "--targets", str(bad)])
    assert exit_code == 1
    assert "markers" in capsys.readouterr().err


def test_main_fails_cleanly_when_the_report_has_no_table(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report = tmp_path / "latest.md"
    report.write_text("# Eval report\n\nno table here\n", encoding="utf-8")
    target = tmp_path / "README.md"
    target.write_text(
        "before\n<!-- eval-table:start -->\nold\n<!-- eval-table:end -->\nafter\n",
        encoding="utf-8",
    )

    exit_code = uet.main(["--report", str(report), "--targets", str(target)])
    assert exit_code == 1
    assert "no Markdown table" in capsys.readouterr().err


def test_default_targets_and_the_real_report_round_trip(tmp_path: Path) -> None:
    """Guards the real contract: the committed latest.md has a table, and both real docs
    (README.md, docs/EVALS.md) still carry the markers the script writes between."""
    real_report = REPO_ROOT / "backend" / "evals" / "reports" / "latest.md"
    table = uet.first_table(real_report.read_text(encoding="utf-8"))
    assert table.startswith("|")

    for doc in (REPO_ROOT / "README.md", REPO_ROOT / "docs" / "EVALS.md"):
        text = doc.read_text(encoding="utf-8")
        assert uet.START in text
        assert uet.END in text
        # The round trip itself is exercised on a copy, never on the real files.
        copy = tmp_path / doc.name
        copy.write_text(text, encoding="utf-8")
        new_text = uet.replace_between_markers(copy.read_text(encoding="utf-8"), table)
        assert uet.START in new_text
        assert uet.END in new_text
