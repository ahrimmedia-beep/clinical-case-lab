#!/usr/bin/env python3
"""Copy the first Markdown table of the eval report into the docs that show it.

The table replaces whatever sits between <!-- eval-table:start --> and <!-- eval-table:end -->.
Run after every live eval:  python3 scripts/update_eval_tables.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
START = "<!-- eval-table:start -->"
END = "<!-- eval-table:end -->"


def first_table(markdown: str) -> str:
    block: list[str] = []
    for line in markdown.splitlines():
        if line.lstrip().startswith("|"):
            block.append(line.rstrip())
        elif block:
            break
    if len(block) < 3:
        raise ValueError("the report has no Markdown table with at least one data row")
    return "\n".join(block)


def replace_between_markers(text: str, body: str) -> str:
    start = text.find(START)
    end = text.find(END)
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"markers {START} ... {END} not found")
    return f"{text[: start + len(START)]}\n{body}\n{text[end:]}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Copy the eval table into the docs.")
    parser.add_argument("--report", type=Path, default=ROOT / "backend/evals/reports/latest.md")
    parser.add_argument(
        "--targets", type=Path, nargs="+", default=[ROOT / "README.md", ROOT / "docs/EVALS.md"]
    )
    args = parser.parse_args(argv)
    try:
        table = first_table(args.report.read_text(encoding="utf-8"))
        for target in args.targets:
            old = target.read_text(encoding="utf-8")
            new = replace_between_markers(old, table)
            if new != old:
                target.write_text(new, encoding="utf-8")
            print(f"{'updated' if new != old else 'unchanged'}: {target}")
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
