#!/usr/bin/env python3
"""Fail when README.md or docs/**/*.md mention a repo path (in backticks) that does not exist.

Keeps the docs honest while code moves. Paths with glob/placeholder characters (* < > { } $)
and git-ignored paths are skipped. Run: python3 scripts/check_doc_paths.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOTS = ("backend/", "web/", "infra/", "scripts/", "schemas/", "docs/", ".github/")
TICKED = re.compile(r"`([^`\s]+)`")
SKIP_CHARS = set("*<>{}$")


def doc_files() -> list[Path]:
    files = [ROOT / "README.md"] if (ROOT / "README.md").exists() else []
    docs = ROOT / "docs"
    if docs.exists():
        files += sorted(p for p in docs.rglob("*.md") if "plans" not in p.parts)
    return files


def is_ignored(rel: str) -> bool:
    return subprocess.run(["git", "check-ignore", "-q", rel], cwd=ROOT, check=False).returncode == 0


def main() -> int:
    missing: list[str] = []
    for doc in doc_files():
        for number, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
            for token in TICKED.findall(line):
                rel = token.rstrip(".,:;").rstrip("/")
                if not rel.startswith(REPO_ROOTS) or SKIP_CHARS & set(rel):
                    continue
                if not (ROOT / rel).exists() and not is_ignored(rel):
                    missing.append(f"{doc.relative_to(ROOT)}:{number}: `{token}` does not exist")
    for item in missing:
        print(item)
    print(f"doc paths: {'FAIL' if missing else 'OK'} ({len(missing)} missing)")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
