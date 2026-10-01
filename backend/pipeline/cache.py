"""Result cache for POST /api/extract (spec §10 step 2).

Key = sha256 of (raw text, provider, model, PROMPT_VERSION). The same text with the same model and
prompt version gives the same draft, so a repeat answers instantly and costs nothing; the
`/studio` samples are pre-warmed after a deploy (`python -m pipeline.cli prewarm`).

Two layers: an in-memory LRU per process (a Cloud Run instance) and an optional directory
(`EXTRACT_CACHE_DIR`) for local runs and the CLI. Only the de-identified response is stored; the
raw text appears nowhere except inside the hash.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections import OrderedDict
from functools import lru_cache
from pathlib import Path

from pydantic import ValidationError

from app.schemas.extract import ExtractResponse

CACHE_DIR_ENV = "EXTRACT_CACHE_DIR"
MAX_ITEMS = 128


def cache_key(text: str, provider: str, model: str, prompt_version: str) -> str:
    # JSON keeps field boundaries unambiguous ("ab"+"c" never equals "a"+"bc").
    payload = json.dumps([text, provider, model, prompt_version], ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ExtractCache:
    def __init__(self, max_items: int = MAX_ITEMS, directory: Path | None = None) -> None:
        self.max_items = max_items
        self.directory = directory
        self._items: OrderedDict[str, ExtractResponse] = OrderedDict()

    def __len__(self) -> int:
        return len(self._items)

    def get(self, key: str) -> ExtractResponse | None:
        if key in self._items:
            self._items.move_to_end(key)
            return self._items[key]
        found = self._read(key)
        if found is not None:
            self._remember(key, found)
        return found

    def put(self, key: str, response: ExtractResponse) -> None:
        self._remember(key, response)
        if self.directory is not None:
            self.directory.mkdir(parents=True, exist_ok=True)
            tmp = self.directory / f"{key}.json.tmp"
            tmp.write_text(response.model_dump_json(), encoding="utf-8")
            tmp.replace(self.directory / f"{key}.json")  # atomic: never a half-written entry

    def _remember(self, key: str, response: ExtractResponse) -> None:
        self._items[key] = response
        self._items.move_to_end(key)
        while len(self._items) > self.max_items:
            self._items.popitem(last=False)

    def _read(self, key: str) -> ExtractResponse | None:
        if self.directory is None:
            return None
        path = self.directory / f"{key}.json"
        try:
            return ExtractResponse.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError):
            return None  # missing or unreadable entry = a miss


@lru_cache(maxsize=1)
def get_extract_cache() -> ExtractCache:
    directory = os.environ.get(CACHE_DIR_ENV, "").strip()
    return ExtractCache(directory=Path(directory) if directory else None)
