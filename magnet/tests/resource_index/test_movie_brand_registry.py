"""Movie brand-family registry contracts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from magnet.resource_index.adapters.movie_brand_registry import (
    load_movie_brand_registry,
)
from magnet.resource_index.errors import ResourceIndexError
from magnet.resource_index.pipeline.movie_brand_probe import _title


def test_builtin_brand_registry_separates_mirrors_candidates_and_portals() -> None:
    registry = load_movie_brand_registry()
    sixv = registry.get("sixv")
    runtime = registry.runtime_endpoints(
        brand_id="sixv",
        source_id="sixv",
        parser_variant="sixv_legacy",
    )
    assert [item.origin for item in runtime] == [
        "https://www.6v520.com",
        "https://www.6v520.net",
        "https://www.6v520.cc",
    ]
    assert all(item.runtime_enabled for item in runtime)
    assert any(item.state == "candidate" and item.origin == "https://www.xb6v.com" for item in sixv.endpoints)
    assert registry.get("dianyingtiantang_nav").content_kinds == ("discovery",)
    assert registry.get("dytt8").brand_id != registry.get("dytt8899").brand_id


def test_brand_probe_decodes_gb2312_title_with_gb18030() -> None:
    content = (
        '<meta charset="gb2312"><title>电影天堂最新电影</title>'
    ).encode("gb18030")
    assert _title(content) == "电影天堂最新电影"


def test_brand_registry_rejects_duplicate_origin(tmp_path: Path) -> None:
    payload = {
        "schema_version": "movie-source-brands/1",
        "verified_at": "2026-07-26T00:00:00Z",
        "brands": [
            {
                "brand_id": "one",
                "label": "One",
                "content_kinds": ["movie"],
                "strategy": "test",
                "endpoints": [
                    {
                        "endpoint_id": "one-a",
                        "origin": "https://example.com",
                        "role": "primary",
                        "state": "active",
                        "parser_variant": "test",
                        "priority": 1,
                        "source_ids": ["one"],
                        "evidence": "test",
                    }
                ],
            },
            {
                "brand_id": "two",
                "label": "Two",
                "content_kinds": ["series"],
                "strategy": "test",
                "endpoints": [
                    {
                        "endpoint_id": "two-a",
                        "origin": "https://example.com",
                        "role": "primary",
                        "state": "active",
                        "parser_variant": "test",
                        "priority": 1,
                        "source_ids": ["two"],
                        "evidence": "test",
                    }
                ],
            },
        ],
    }
    path = tmp_path / "brands.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    load_movie_brand_registry.cache_clear()
    with pytest.raises(ResourceIndexError, match="multiple endpoints"):
        load_movie_brand_registry(path)
    load_movie_brand_registry.cache_clear()
