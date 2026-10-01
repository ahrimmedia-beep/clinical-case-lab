from __future__ import annotations

from pathlib import Path

import pytest

from app.schemas.extract import ExtractResponse
from pipeline.cache import CACHE_DIR_ENV, ExtractCache, cache_key, get_extract_cache
from pipeline.providers.fake import SAMPLE_TEXT_FILE, FakeProvider
from pipeline.run import run_pipeline

SAMPLE = SAMPLE_TEXT_FILE.read_text()


@pytest.fixture(autouse=True)
def fresh_cache() -> None:
    get_extract_cache.cache_clear()


@pytest.fixture
async def response() -> ExtractResponse:
    return await run_pipeline(SAMPLE, FakeProvider.default())


def test_key_is_sha256_of_text_provider_model_and_prompt_version() -> None:
    base = cache_key("some text", "gemini", "gemini-3.8-flash", "v1")
    assert len(base) == 64 and all(c in "0123456789abcdef" for c in base)
    assert base == cache_key("some text", "gemini", "gemini-3.8-flash", "v1")
    others = {
        cache_key("other text", "gemini", "gemini-3.8-flash", "v1"),
        cache_key("some text", "claude", "gemini-3.8-flash", "v1"),
        cache_key("some text", "gemini", "claude-sonnet-5", "v1"),
        cache_key("some text", "gemini", "gemini-3.8-flash", "v2"),
        # field boundaries matter: "ab"+"c" must not collide with "a"+"bc"
        cache_key("some tex", "tgemini", "gemini-3.8-flash", "v1"),
    }
    assert base not in others and len(others) == 5


def test_memory_cache_is_lru(response: ExtractResponse) -> None:
    cache = ExtractCache(max_items=2)
    cache.put("a", response)
    cache.put("b", response)
    assert cache.get("a") == response  # "a" is now the most recent
    cache.put("c", response)
    assert cache.get("b") is None
    assert cache.get("a") == response and cache.get("c") == response
    assert len(cache) == 2


def test_disk_cache_survives_a_new_process(tmp_path: Path, response: ExtractResponse) -> None:
    first = ExtractCache(max_items=4, directory=tmp_path)
    key = cache_key(SAMPLE, "gemini", "fake-model", "v1")
    first.put(key, response)
    stored = tmp_path / f"{key}.json"
    assert stored.exists()
    assert "Whitfield" not in stored.read_text()  # only the masked response is stored
    second = ExtractCache(max_items=4, directory=tmp_path)
    assert second.get(key) == response


def test_corrupt_disk_entry_is_a_miss(tmp_path: Path) -> None:
    (tmp_path / f"{'0' * 64}.json").write_text("{not json")
    assert ExtractCache(directory=tmp_path).get("0" * 64) is None


def test_get_extract_cache_reads_the_optional_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv(CACHE_DIR_ENV, raising=False)
    assert get_extract_cache().directory is None
    get_extract_cache.cache_clear()
    monkeypatch.setenv(CACHE_DIR_ENV, str(tmp_path / "cache"))
    assert get_extract_cache().directory == tmp_path / "cache"
