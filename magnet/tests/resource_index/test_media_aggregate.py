"""Cross-brand movie and series feed aggregation contracts."""

from __future__ import annotations

import json
from pathlib import Path

from magnet.resource_index.pipeline.media_aggregate import aggregate_media_feeds


def _write_feed(path: Path, source_id: str, items: list[dict]) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "movie-feed/1",
                "source_id": source_id,
                "snapshot_captured_at": "2026-07-26T00:00:00Z",
                "items": items,
                "summary": {},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _item(
    *,
    source_id: str,
    brand_id: str,
    title: str,
    year: int,
    kind: str = "movie",
    update_date: str = "2026-07-25",
    season: int | None = None,
    episode: int | None = None,
    resource: str,
) -> dict:
    return {
        "rank": 1,
        "movie_id": f"movie:{source_id}",
        "source_id": source_id,
        "brand_id": brand_id,
        "source_item_key": f"/{source_id}",
        "detail_url": f"https://{source_id}.example/item",
        "endpoint_origin": f"https://{source_id}.example",
        "listing_title": title,
        "content_kind": kind,
        "series_title": title if kind == "series" else None,
        "season_number": season,
        "episode_number": episode,
        "episode_label": f"第{episode}集" if episode else None,
        "update_status": f"第{episode}集" if episode else None,
        "title": title,
        "original_title": None,
        "year": year,
        "update_date": update_date,
        "release_date": None,
        "duration_minutes": None,
        "countries": [],
        "genres": [],
        "languages": [],
        "directors": [],
        "actors": [],
        "imdb_id": None,
        "douban_rating": None,
        "douban_rating_text": None,
        "douban_url": None,
        "cover_source_url": None,
        "synopsis": None,
        "recommended": False,
        "highlight_labels": [],
        "quality_tags": [],
        "resources": [
            {
                "resource_type": "magnet",
                "provider": "magnet",
                "url": resource,
                "info_hash": resource.rsplit(":", 1)[-1],
                "display_title": title,
                "extraction_code": None,
                "quality_tags": [],
            }
        ],
    }


def test_aggregate_merges_same_movie_across_brands_and_resources(tmp_path: Path) -> None:
    sixv = tmp_path / "sixv.json"
    dytt = tmp_path / "dytt.json"
    _write_feed(
        sixv,
        "sixv",
        [_item(source_id="sixv", brand_id="sixv", title="寒战 1994", year=2026, resource="magnet:?xt=urn:btih:AAA")],
    )
    _write_feed(
        dytt,
        "dytt8899",
        [_item(source_id="dytt8899", brand_id="dytt8899", title="寒战1994", year=2026, resource="magnet:?xt=urn:btih:BBB")],
    )
    result = aggregate_media_feeds([sixv, dytt])
    assert result["summary"]["record_count"] == 1
    item = result["items"][0]
    assert item["source_count"] == 2
    assert item["brand_count"] == 2
    assert len(item["resources"]) == 2
    assert {variant["source_id"] for variant in item["source_variants"]} == {"sixv", "dytt8899"}


def test_aggregate_series_keeps_latest_episode_and_merges_sources(tmp_path: Path) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    _write_feed(
        first,
        "meijumi",
        [
            _item(
                source_id="meijumi",
                brand_id="meijumi",
                title="深信之疑第一季",
                year=2026,
                kind="series",
                season=1,
                episode=1,
                update_date="2026-07-25",
                resource="magnet:?xt=urn:btih:CCC",
            )
        ],
    )
    _write_feed(
        second,
        "sixv-series",
        [
            _item(
                source_id="sixv-series",
                brand_id="sixv",
                title="深信之疑第一季",
                year=2026,
                kind="series",
                season=1,
                episode=2,
                update_date="2026-07-26",
                resource="magnet:?xt=urn:btih:DDD",
            )
        ],
    )
    result = aggregate_media_feeds([first, second], output_path=tmp_path / "media.json")
    assert result["summary"]["series_count"] == 1
    assert result["items"][0]["episode_number"] == 2
    assert result["items"][0]["source_count"] == 2
    assert (tmp_path / "media.json").exists()


def test_aggregate_series_strips_season_suffix_and_does_not_require_imdb_on_both_sources(
    tmp_path: Path,
) -> None:
    meijumi = tmp_path / "meijumi.json"
    sixv = tmp_path / "sixv-series.json"
    first = _item(
        source_id="meijumi",
        brand_id="meijumi",
        title="犯罪心理：演变 第十八季",
        year=2026,
        kind="series",
        season=19,
        episode=10,
        update_date="2026-07-24",
        resource="magnet:?xt=urn:btih:EEE",
    )
    first["series_title"] = "犯罪心理：演变第十九季"
    second = _item(
        source_id="sixv-series",
        brand_id="sixv",
        title="犯罪心理：演变",
        year=2026,
        kind="series",
        season=None,
        episode=None,
        update_date="2026-07-24",
        resource="magnet:?xt=urn:btih:FFF",
    )
    second["series_title"] = "犯罪心理：演变 第十九季"
    second["imdb_id"] = "tt36021078"
    _write_feed(meijumi, "meijumi", [first])
    _write_feed(sixv, "sixv-series", [second])

    result = aggregate_media_feeds([meijumi, sixv])
    assert result["summary"]["record_count"] == 1
    assert result["summary"]["multi_source_count"] == 1
    merged = result["items"][0]
    assert merged["season_number"] == 19
    assert merged["episode_number"] == 10
    assert merged["source_count"] == 2
    assert len(merged["resources"]) == 2
