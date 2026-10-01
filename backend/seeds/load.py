"""POST the showcase cases to a running API. Idempotent: the API dedups by content hash.

Files load in name order and the catalogue lists newest first, so the last file
(`03-lam.json`, the rare-disease hero) leads the catalogue.

Usage (from backend/): uv run python -m seeds.load --api http://localhost:8000
Production ingest is key-protected: the `X-Internal-Key` header is sent from `--key`
(default `$INTERNAL_API_KEY`) when set.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Iterable
from pathlib import Path
from time import sleep
from typing import Any

import httpx

CASES_DIR = Path(__file__).parent / "cases"
RETRYABLE = {429, 500, 502, 503, 504}


def seed_files() -> list[Path]:
    return sorted(CASES_DIR.glob("*.json"))


def api_client(
    base_url: str, key: str | None, *, transport: httpx.BaseTransport | None = None
) -> httpx.Client:
    headers = {"X-Internal-Key": key} if key else {}
    return httpx.Client(base_url=base_url, headers=headers, timeout=30.0, transport=transport)


def post_with_retry(
    client: httpx.Client, payload: dict[str, Any], attempts: int = 6
) -> httpx.Response:
    """Retry while the API starts or is briefly unavailable: 2 s, 4 s, ... capped at 30 s."""
    delay = 2.0
    for attempt in range(1, attempts + 1):
        try:
            response = client.post("/api/cases", json=payload)
            if response.status_code not in RETRYABLE or attempt == attempts:
                return response
        except httpx.TransportError:
            if attempt == attempts:
                raise
        sleep(delay)
        delay = min(delay * 2, 30.0)
    raise RuntimeError("unreachable")


def load_seeds(client: httpx.Client, files: Iterable[Path]) -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []
    for path in files:
        response = post_with_retry(client, json.loads(path.read_text(encoding="utf-8")))
        if response.status_code not in (200, 201):
            raise SystemExit(f"{path.name}: HTTP {response.status_code} {response.text[:500]}")
        body = response.json()
        results.append((str(body["slug"]), "created" if body["created"] else "exists"))
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Load the showcase cases into a running API.")
    parser.add_argument("--api", default=os.environ.get("API_BASE_URL", "http://localhost:8000"))
    parser.add_argument("--key", default=os.environ.get("INTERNAL_API_KEY"))
    args = parser.parse_args(argv)
    with api_client(args.api, args.key) as client:
        for slug, status in load_seeds(client, seed_files()):
            print(f"{status:8} {slug}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
