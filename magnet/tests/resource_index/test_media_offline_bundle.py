from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

from PIL import Image
import pytest

from magnet.resource_index.errors import CONFIG_ERROR, ResourceIndexError
from magnet.resource_index.pipeline.media_offline_bundle import (
    audit_media_app_bundle,
    build_media_app_bundle,
)


def _image_bytes() -> bytes:
    image = Image.new("RGB", (900, 1350), "navy")
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _item(index: int, *, kind: str, season: int | None = None) -> dict:
    resource = {
        "resource_type": "magnet",
        "provider": "magnet",
        "url": f"magnet:?xt=urn:btih:{index:040d}&dn=Show%20S{(season or 1):02d}E{index + 1:02d}%201080p",
        "info_hash": f"{index:040d}",
        "display_title": f"S{(season or 1):02d}E{index + 1:02d} · 1080P",
        "extraction_code": None,
        "quality_tags": ["1080p"],
        "season_number": season,
        "episode_start": index + 1,
        "episode_end": index + 1,
        "episode_label": f"S{(season or 1):02d}E{index + 1:02d}",
        "title_source": "magnet_dn",
    }
    return {
        "rank": index + 1,
        "movie_id": f"movie:{index}",
        "source_id": "fixture",
        "source_item_key": f"/{index}",
        "detail_url": f"https://fixture.example/{index}",
        "listing_title": f"Fixture {index}",
        "content_kind": kind,
        "series_title": "Fixture" if kind == "series" else None,
        "season_number": season,
        "episode_number": index + 1 if kind == "series" else None,
        "episode_label": resource["episode_label"] if kind == "series" else None,
        "update_status": None,
        "title": f"Fixture {index}",
        "original_title": None,
        "year": 2026,
        "update_date": "2026-07-26",
        "release_date": None,
        "duration_minutes": None,
        "countries": ["美国"],
        "genres": ["剧情"],
        "languages": [],
        "directors": [],
        "actors": [],
        "imdb_id": None,
        "douban_rating": None,
        "douban_rating_text": None,
        "douban_url": None,
        "cover_source_url": f"https://images.example/{index}.png",
        "cover_candidates": [
            {
                "url": f"https://bad.example/{index}.png",
                "referer": f"https://fixture.example/{index}",
            },
            {
                "url": f"https://images.example/{index}.png",
                "referer": f"https://fixture.example/{index}",
            },
        ],
        "synopsis": "Fixture synopsis",
        "recommended": False,
        "highlight_labels": [],
        "quality_tags": ["1080p"],
        "resources": [resource],
    }


def _write_feed(path: Path, *, kind: str, count: int = 2) -> None:
    items = [_item(index, kind=kind, season=1 if kind == "series" else None) for index in range(count)]
    path.write_text(
        json.dumps(
            {
                "schema_version": "media-feed/1",
                "generated_at": "2026-07-26T00:00:00+08:00",
                "content_kind_filter": kind,
                "sources": [],
                "items": items,
                "summary": {"record_count": count},
                "quality": {"status": "pass"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_build_and_reuse_fully_offline_series_bundle(tmp_path: Path) -> None:
    feed = tmp_path / "series.json"
    bundle = tmp_path / "bundle"
    _write_feed(feed, kind="series")
    calls: list[str] = []
    image = _image_bytes()

    def fetch(url: str, referer: str | None) -> bytes:
        calls.append(url)
        assert referer and referer.startswith("https://fixture.example/")
        if url.startswith("https://bad.example/"):
            raise ResourceIndexError(CONFIG_ERROR, "fixture failure", {})
        return image

    first = build_media_app_bundle(
        feed_path=feed,
        output_dir=bundle,
        content_kind="series",
        expected_count=2,
        fetcher=fetch,
    )
    assert first.item_count == 2
    assert first.cover_count == 2
    assert first.downloaded == 2
    assert first.reused == 0
    assert len(calls) == 4
    assert len(list((bundle / "covers").glob("*.jpg"))) == 1

    payload = json.loads((bundle / "feed.json").read_text(encoding="utf-8"))
    assert payload["summary"]["offline_ready"] is True
    assert payload["summary"]["cover_count"] == 2
    assert all(item["cover_asset_path"].startswith("covers/") for item in payload["items"])
    assert all(item["cover_content_hash"] for item in payload["items"])
    assert audit_media_app_bundle(
        bundle_dir=bundle,
        content_kind="series",
        expected_count=2,
    )["status"] == "pass"

    calls.clear()
    second = build_media_app_bundle(
        feed_path=feed,
        output_dir=bundle,
        content_kind="series",
        expected_count=2,
        fetcher=fetch,
    )
    assert second.downloaded == 0
    assert second.reused == 2
    assert calls == []


def test_app_bundle_rejects_missing_required_title(tmp_path: Path) -> None:
    feed = tmp_path / "missing-title.json"
    bundle = tmp_path / "bundle"
    _write_feed(feed, kind="movie", count=1)
    payload = json.loads(feed.read_text(encoding="utf-8"))
    payload["items"][0]["title"] = ""
    feed.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ResourceIndexError, match="missing required title"):
        build_media_app_bundle(
            feed_path=feed,
            output_dir=bundle,
            content_kind="movie",
            fetcher=lambda _url, _referer: _image_bytes(),
        )


def test_app_bundle_rejects_missing_required_cover(tmp_path: Path) -> None:
    feed = tmp_path / "missing-cover.json"
    bundle = tmp_path / "bundle"
    _write_feed(feed, kind="movie", count=1)
    payload = json.loads(feed.read_text(encoding="utf-8"))
    payload["items"][0]["cover_source_url"] = None
    payload["items"][0]["cover_candidates"] = []
    feed.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ResourceIndexError, match="missing required cover"):
        build_media_app_bundle(
            feed_path=feed,
            output_dir=bundle,
            content_kind="movie",
            fetcher=lambda _url, _referer: _image_bytes(),
        )


def test_app_bundle_filters_unsupported_download_player_resources(tmp_path: Path) -> None:
    feed = tmp_path / "movie.json"
    bundle = tmp_path / "bundle"
    _write_feed(feed, kind="movie", count=1)
    payload = json.loads(feed.read_text(encoding="utf-8"))
    payload["items"][0]["resources"].append(
        {
            "resource_type": "download",
            "provider": "dytt",
            "url": "https://download.example/file.html",
            "display_title": "下载页",
            "quality_tags": [],
        }
    )
    feed.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    result = build_media_app_bundle(
        feed_path=feed,
        output_dir=bundle,
        content_kind="movie",
        expected_count=1,
        fetcher=lambda _url, _referer: _image_bytes(),
    )
    assert result.resource_count == 1
    app_feed = json.loads((bundle / "feed.json").read_text(encoding="utf-8"))
    assert [resource["resource_type"] for resource in app_feed["items"][0]["resources"]] == ["magnet"]


def test_app_bundle_rejects_item_with_only_unsupported_resources(tmp_path: Path) -> None:
    feed = tmp_path / "movie.json"
    bundle = tmp_path / "bundle"
    _write_feed(feed, kind="movie", count=1)
    payload = json.loads(feed.read_text(encoding="utf-8"))
    payload["items"][0]["resources"] = [
        {
            "resource_type": "player",
            "provider": "dytt",
            "url": "https://player.example/watch",
            "display_title": "在线播放",
            "quality_tags": [],
        }
    ]
    feed.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    try:
        build_media_app_bundle(
            feed_path=feed,
            output_dir=bundle,
            content_kind="movie",
            expected_count=1,
            fetcher=lambda _url, _referer: _image_bytes(),
        )
    except ResourceIndexError as exc:
        assert exc.message == "media feed does not contain enough App-supported items"
    else:
        raise AssertionError("unsupported-only App item should fail")


def test_app_bundle_refills_target_after_skipping_unsupported_item(tmp_path: Path) -> None:
    feed = tmp_path / "movie.json"
    bundle = tmp_path / "bundle"
    _write_feed(feed, kind="movie", count=2)
    payload = json.loads(feed.read_text(encoding="utf-8"))
    payload["items"][0]["resources"] = [
        {
            "resource_type": "download",
            "provider": "dytt",
            "url": "https://download.example/file.html",
            "display_title": "下载页",
            "quality_tags": [],
        }
    ]
    feed.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    result = build_media_app_bundle(
        feed_path=feed,
        output_dir=bundle,
        content_kind="movie",
        expected_count=1,
        fetcher=lambda _url, _referer: _image_bytes(),
    )
    app_feed = json.loads((bundle / "feed.json").read_text(encoding="utf-8"))
    assert result.item_count == 1
    assert app_feed["items"][0]["movie_id"] == "movie:1"
    assert app_feed["items"][0]["rank"] == 1


def test_bundle_audit_rejects_cross_season_resource(tmp_path: Path) -> None:
    feed = tmp_path / "series.json"
    bundle = tmp_path / "bundle"
    _write_feed(feed, kind="series", count=1)
    build_media_app_bundle(
        feed_path=feed,
        output_dir=bundle,
        content_kind="series",
        expected_count=1,
        fetcher=lambda _url, _referer: _image_bytes(),
    )
    payload = json.loads((bundle / "feed.json").read_text(encoding="utf-8"))
    payload["items"][0]["resources"][0]["season_number"] = 2
    (bundle / "feed.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    report = audit_media_app_bundle(
        bundle_dir=bundle,
        content_kind="series",
        expected_count=1,
        raise_on_error=False,
    )
    assert report["status"] == "fail"
    assert any(error["code"] == "CROSS_SEASON_RESOURCE" for error in report["errors"])


def test_incomplete_cover_build_does_not_write_final_feed(tmp_path: Path) -> None:
    feed = tmp_path / "movie.json"
    bundle = tmp_path / "bundle"
    _write_feed(feed, kind="movie", count=1)

    def fail(_url: str, _referer: str | None) -> bytes:
        raise ResourceIndexError(CONFIG_ERROR, "unavailable", {})

    try:
        build_media_app_bundle(
            feed_path=feed,
            output_dir=bundle,
            content_kind="movie",
            expected_count=1,
            fetcher=fail,
        )
    except ResourceIndexError as exc:
        assert exc.message == "offline media covers are incomplete"
    else:
        raise AssertionError("cover build should fail")
    assert not (bundle / "feed.json").exists()
