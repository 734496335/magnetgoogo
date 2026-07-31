from __future__ import annotations

import hashlib
import json
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from magnet.resource_index.errors import ResourceIndexError
from magnet.resource_index.pipeline.magnet_only import (
    build_magnet_only_media_feeds,
    seed_media_cover_bundle_cache,
)


def _resource(info_hash: str, *, kind: str = "magnet") -> dict[str, object]:
    if kind == "cloud":
        return {
            "resource_type": "cloud",
            "provider": "quark",
            "url": "https://pan.quark.cn/s/example",
            "info_hash": None,
            "display_title": "cloud",
            "extraction_code": None,
            "quality_tags": [],
        }
    return {
        "resource_type": "magnet",
        "provider": "magnet",
        "url": f"magnet:?xt=urn:btih:{info_hash}&dn=fixture",
        "info_hash": info_hash,
        "display_title": "fixture",
        "extraction_code": None,
        "quality_tags": [],
    }


def _feed(path: Path, kind: str, items: list[dict[str, object]]) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "media-feed/1",
                "content_kind_filter": kind,
                "generated_at": "2026-07-31T00:00:00Z",
                "sources": [],
                "items": items,
                "summary": {
                    "record_count": len(items),
                    "movie_count": len(items) if kind == "movie" else 0,
                    "series_count": len(items) if kind == "series" else 0,
                    "available_movie_count": len(items) if kind == "movie" else 0,
                    "available_series_count": len(items) if kind == "series" else 0,
                    "resource_count": sum(len(item["resources"]) for item in items),
                },
                "quality": {"status": "pass"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _item(rank: int, title: str, resources: list[dict[str, object]]) -> dict[str, object]:
    return {
        "rank": rank,
        "movie_id": f"movie:{rank}",
        "content_kind": "movie",
        "title": title,
        "cover_source_url": f"https://img.example/{rank}.jpg",
        "resources": resources,
    }


def test_build_magnet_only_media_feeds_filters_cloud_and_drops_empty(tmp_path: Path) -> None:
    movie_path = tmp_path / "movies.json"
    series_path = tmp_path / "series.json"
    h1 = "1" * 40
    h2 = "2" * 40
    _feed(
        movie_path,
        "movie",
        [
            _item(1, "Movie", [_resource(h1), _resource("0" * 40, kind="cloud")]),
        ],
    )
    series_item = _item(1, "Series", [_resource(h2)])
    series_item["content_kind"] = "series"
    cloud_only = _item(2, "Cloud Only", [_resource("0" * 40, kind="cloud")])
    cloud_only["content_kind"] = "series"
    _feed(series_path, "series", [series_item, cloud_only])

    report = build_magnet_only_media_feeds(
        movie_feed_path=movie_path,
        series_feed_path=series_path,
        output_dir=tmp_path / "out",
    )
    movies = json.loads(Path(report["movie_feed"]).read_text(encoding="utf-8"))
    series = json.loads(Path(report["series_feed"]).read_text(encoding="utf-8"))
    assert report["status"] == "pass"
    assert report["total_item_count"] == 2
    assert report["total_magnet_resource_count"] == 2
    assert movies["summary"]["available_movie_count"] == 1
    assert movies["summary"]["available_series_count"] == 1
    assert len(series["items"]) == 1
    assert series["items"][0]["rank"] == 1
    assert all(resource["resource_type"] == "magnet" for resource in movies["items"][0]["resources"])


def test_build_magnet_only_media_feeds_rejects_duplicate_hash(tmp_path: Path) -> None:
    movie_path = tmp_path / "movies.json"
    series_path = tmp_path / "series.json"
    duplicate = "a" * 40
    _feed(movie_path, "movie", [_item(1, "Movie", [_resource(duplicate)])])
    series_item = _item(1, "Series", [_resource(duplicate)])
    series_item["content_kind"] = "series"
    _feed(series_path, "series", [series_item])
    with pytest.raises(ResourceIndexError, match="duplicate magnet info hash"):
        build_magnet_only_media_feeds(
            movie_feed_path=movie_path,
            series_feed_path=series_path,
            output_dir=tmp_path / "out",
        )


def test_seed_media_cover_bundle_cache_reuses_verified_assets(tmp_path: Path) -> None:
    feed_path = tmp_path / "movies.json"
    item = _item(1, "Movie", [_resource("e" * 40)])
    item["cover_candidates"] = [{"url": "https://img.example/1.jpg"}]
    _feed(feed_path, "movie", [item])
    probe_dir = tmp_path / "probe"
    source_cover = probe_dir / "covers" / "source.jpg"
    source_cover.parent.mkdir(parents=True)
    buffer = BytesIO()
    Image.new("RGB", (2, 3)).save(buffer, format="JPEG")
    payload = buffer.getvalue()
    digest = hashlib.sha256(payload).hexdigest()
    source_cover.write_bytes(payload)
    (probe_dir / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "source-cover-assets/1",
                "source_id": "fixture",
                "assets": {
                    "https://img.example/1.jpg": {
                        "path": "covers/source.jpg",
                        "mime_type": "image/jpeg",
                        "content_hash": digest,
                        "width": 2,
                        "height": 3,
                        "byte_size": len(payload),
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "bundle"
    report = seed_media_cover_bundle_cache(
        feed_path=feed_path,
        output_dir=output,
        probe_dirs=[probe_dir],
    )
    assert report["status"] == "pass"
    assert report["covered_item_count"] == 1
    assert report["unique_asset_count"] == 1
    assert (output / "covers" / f"{digest}.jpg").read_bytes() == payload


def test_build_magnet_only_media_feeds_rejects_hash_mismatch(tmp_path: Path) -> None:
    movie_path = tmp_path / "movies.json"
    series_path = tmp_path / "series.json"
    resource = _resource("b" * 40)
    resource["info_hash"] = "c" * 40
    _feed(movie_path, "movie", [_item(1, "Movie", [resource])])
    series_item = _item(1, "Series", [_resource("d" * 40)])
    series_item["content_kind"] = "series"
    _feed(series_path, "series", [series_item])
    with pytest.raises(ResourceIndexError, match="does not match URL"):
        build_magnet_only_media_feeds(
            movie_feed_path=movie_path,
            series_feed_path=series_path,
            output_dir=tmp_path / "out",
        )
