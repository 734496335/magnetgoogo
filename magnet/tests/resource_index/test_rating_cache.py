from __future__ import annotations

import json
import time
from pathlib import Path

from magnet.rating_resolver.cache import JsonCache


def test_rating_cache_hashes_long_multibyte_keys_with_bounded_filename(tmp_path: Path) -> None:
    cache = JsonCache(tmp_path)
    key = "lookup-match-gate-v2::" + "东京出租车/魔法坏女巫/浴血黑帮" * 40
    payload = {"status": "ok", "score": 8.1}

    cache.set(key, payload)

    files = list(tmp_path.glob("*.json"))
    assert len(files) == 1
    assert len(files[0].name.encode("utf-8")) < 180
    assert cache.get(key) == payload


def test_rating_cache_reads_compatible_legacy_filename(tmp_path: Path) -> None:
    cache = JsonCache(tmp_path)
    key = "legacy::short-title"
    legacy = cache._legacy_path(key)
    legacy.write_text(
        json.dumps({"_cached_at": time.time(), "payload": {"value": 7.5}}),
        encoding="utf-8",
    )

    assert cache.get(key) == {"value": 7.5}


def test_rating_cache_ignores_expired_entry(tmp_path: Path) -> None:
    cache = JsonCache(tmp_path, ttl_seconds=1)
    key = "expired"
    path = cache._path(key)
    path.write_text(
        json.dumps({"_cached_at": time.time() - 10, "payload": {"value": 1}}),
        encoding="utf-8",
    )

    assert cache.get(key) is None
