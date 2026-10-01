#!/usr/bin/env python3
"""Public-repo hygiene gate: no Cyrillic text, no secret-shaped strings, no committed env files.

Scans every file tracked by git (text files only). Run: python3 scripts/check_hygiene.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CYRILLIC = re.compile("[" + chr(0x0400) + "-" + chr(0x04FF) + "]")  # ASCII-only source on purpose
SECRET_PATTERNS = {
    "Anthropic API key": re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"),
    "OpenAI API key": re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{32,}"),
    "Google API key": re.compile(r"AIza[0-9A-Za-z_-]{35}"),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "GCP service account key": re.compile(r'"type":\s*"service_account"'),
    "Telegram bot token": re.compile(r"\b\d{8,10}:AA[0-9A-Za-z_-]{33}\b"),
}
ENV_FILE = re.compile(r"(^|/)\.env(\.(?!example$)[^/]+)?$")
BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".woff", ".woff2", ".ttf", ".pdf"}


def tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True
    ).stdout.decode()
    return [path for path in out.split("\0") if path]


def scan_line(line: str) -> list[str]:
    """Problems on one line of text, without file/line context (unit-testable in isolation)."""
    problems: list[str] = []
    if CYRILLIC.search(line):
        problems.append("Cyrillic text (the public repo is English only)")
    for name, pattern in SECRET_PATTERNS.items():
        if pattern.search(line):
            problems.append(f"looks like a {name}")
    return problems


def scan(rel: str) -> list[str]:
    problems: list[str] = []
    if ENV_FILE.search(rel):
        problems.append(f"{rel}: env files must not be committed")
    path = ROOT / rel
    if path.suffix.lower() in BINARY_SUFFIXES or not path.is_file():
        return problems
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return problems
    for number, line in enumerate(text.splitlines(), 1):
        for problem in scan_line(line):
            problems.append(f"{rel}:{number}: {problem}")
    return problems


def main() -> int:
    problems = [problem for rel in tracked_files() for problem in scan(rel)]
    for problem in problems:
        print(problem)
    print(f"hygiene: {'FAIL' if problems else 'OK'} ({len(problems)} problems)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
