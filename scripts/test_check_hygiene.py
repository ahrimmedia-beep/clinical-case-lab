#!/usr/bin/env python3
"""Unit tests for scripts/check_hygiene.py. Run: python3 scripts/test_check_hygiene.py
(or: uv run --project backend pytest scripts/test_check_hygiene.py)
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_hygiene import scan_line  # noqa: E402


class ScanLineTests(unittest.TestCase):
    def test_clean_line_has_no_problems(self) -> None:
        self.assertEqual(scan_line("Everything in containers:"), [])

    def test_cyrillic_is_flagged(self) -> None:
        problems = scan_line("\u0421\u0434\u0430\u0451\u043c 02.10")
        self.assertEqual(len(problems), 1)
        self.assertIn("Cyrillic", problems[0])

    def test_anthropic_key_shape_is_flagged(self) -> None:
        problems = scan_line("ANTHROPIC_API_KEY=sk-ant-" + "a" * 24)
        self.assertEqual(len(problems), 1)
        self.assertIn("Anthropic API key", problems[0])


if __name__ == "__main__":
    unittest.main()
