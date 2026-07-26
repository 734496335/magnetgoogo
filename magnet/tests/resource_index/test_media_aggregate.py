"""Cross-brand movie and series feed aggregation contracts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from magnet.resource_index.errors import ResourceIndexError
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


def test_aggregate_enforces_independent_movie_and_series_quotas(tmp_path: Path) -> None:
    movies = tmp_path / "movies.json"
    series = tmp_path / "series.json"
    _write_feed(
        movies,
        "movie-source",
        [
            _item(
                source_id=f"movie-{index}",
                brand_id="movies",
                title=f"电影{index:03d}",
                year=2026,
                update_date="2026-07-01",
                resource=f"magnet:?xt=urn:btih:M{index:039d}",
            )
            for index in range(110)
        ],
    )
    _write_feed(
        series,
        "series-source",
        [
            _item(
                source_id=f"series-{index}",
                brand_id="series",
                title=f"剧集{index:03d}第一季",
                year=2026,
                kind="series",
                season=1,
                episode=index + 1,
                update_date="2026-07-26",
                resource=f"magnet:?xt=urn:btih:S{index:039d}",
            )
            for index in range(120)
        ],
    )

    result = aggregate_media_feeds(
        [movies, series],
        output_path=tmp_path / "combined.json",
        movie_output_path=tmp_path / "movies-100.json",
        series_output_path=tmp_path / "series-100.json",
        movie_limit=100,
        series_limit=100,
        strict_kind_limits=True,
    )

    assert result["summary"]["record_count"] == 200
    assert result["summary"]["movie_count"] == 100
    assert result["summary"]["series_count"] == 100
    assert result["summary"]["available_movie_count"] == 110
    assert result["summary"]["available_series_count"] == 120
    assert json.loads((tmp_path / "movies-100.json").read_text(encoding="utf-8"))["summary"]["movie_count"] == 100
    assert json.loads((tmp_path / "series-100.json").read_text(encoding="utf-8"))["summary"]["series_count"] == 100


def test_aggregate_strict_kind_quota_fails_instead_of_silently_underfilling(tmp_path: Path) -> None:
    feed = tmp_path / "feed.json"
    _write_feed(
        feed,
        "only-movies",
        [_item(source_id="one", brand_id="one", title="唯一电影", year=2026, resource="magnet:?xt=urn:btih:ONE")],
    )
    with pytest.raises(ResourceIndexError, match="strict kind limits") as exc_info:
        aggregate_media_feeds(
            [feed],
            movie_limit=1,
            series_limit=1,
            strict_kind_limits=True,
        )
    assert exc_info.value.context["series"] == {"requested": 1, "available": 0}


def test_aggregate_deduplicates_same_info_hash_and_source_variant(tmp_path: Path) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    left = _item(
        source_id="sixv",
        brand_id="sixv",
        title="同一电影",
        year=2026,
        resource="magnet:?xt=urn:btih:ABC&dn=left",
    )
    left["resources"][0]["info_hash"] = "ABC"
    right = _item(
        source_id="sixv",
        brand_id="sixv",
        title="同一电影",
        year=2026,
        update_date="2026-07-26",
        resource="magnet:?xt=urn:btih:ABC&dn=right",
    )
    right["source_item_key"] = left["source_item_key"]
    right["resources"][0]["info_hash"] = "abc"
    right["resources"][0]["quality_tags"] = ["1080p"]
    _write_feed(first, "sixv", [left])
    _write_feed(second, "sixv", [right])

    result = aggregate_media_feeds([first, second])
    merged = result["items"][0]
    assert len(merged["resources"]) == 1
    assert merged["resources"][0]["quality_tags"] == ["1080p"]
    assert len(merged["source_variants"]) == 1
    assert merged["source_count"] == 1


def test_aggregate_missing_season_is_order_independent_when_multiple_seasons_exist(tmp_path: Path) -> None:
    paths = [tmp_path / name for name in ("unknown.json", "s1.json", "s2.json")]
    unknown = _item(
        source_id="unknown",
        brand_id="unknown",
        title="多季剧集",
        year=2026,
        kind="series",
        season=None,
        episode=5,
        resource="magnet:?xt=urn:btih:UNKNOWN",
    )
    season_one = _item(
        source_id="s1",
        brand_id="s1",
        title="多季剧集第一季",
        year=2025,
        kind="series",
        season=1,
        episode=10,
        resource="magnet:?xt=urn:btih:SEASON1",
    )
    season_two = _item(
        source_id="s2",
        brand_id="s2",
        title="多季剧集第二季",
        year=2026,
        kind="series",
        season=2,
        episode=5,
        resource="magnet:?xt=urn:btih:SEASON2",
    )
    for path, source, item in zip(paths, ("unknown", "s1", "s2"), (unknown, season_one, season_two)):
        _write_feed(path, source, [item])

    forward = aggregate_media_feeds(paths)
    reverse = aggregate_media_feeds(reversed(paths))
    assert forward["summary"]["record_count"] == 3
    assert reverse["summary"]["record_count"] == 3
    assert {item["media_identity"] for item in forward["items"]} == {
        item["media_identity"] for item in reverse["items"]
    }


def test_unknown_season_cannot_bridge_conflicting_title_and_imdb_candidates(tmp_path: Path) -> None:
    first = tmp_path / "season-one.json"
    bridge = tmp_path / "unknown.json"
    second = tmp_path / "season-two.json"
    season_one = _item(
        source_id="s1",
        brand_id="one",
        title="桥接剧第一季",
        year=2025,
        kind="series",
        season=1,
        episode=10,
        resource="magnet:?xt=urn:btih:BRIDGE1",
    )
    season_two = _item(
        source_id="s2",
        brand_id="two",
        title="另一个译名第二季",
        year=2026,
        kind="series",
        season=2,
        episode=5,
        resource="magnet:?xt=urn:btih:BRIDGE2",
    )
    season_two["imdb_id"] = "tt1234567"
    unknown = _item(
        source_id="unknown",
        brand_id="unknown",
        title="桥接剧",
        year=2026,
        kind="series",
        season=None,
        episode=5,
        resource="magnet:?xt=urn:btih:BRIDGE0",
    )
    unknown["imdb_id"] = "tt1234567"
    _write_feed(first, "s1", [season_one])
    _write_feed(bridge, "unknown", [unknown])
    _write_feed(second, "s2", [season_two])

    result = aggregate_media_feeds([first, bridge, second])
    assert result["summary"]["record_count"] == 3
    assert sorted(item["season_number"] or 0 for item in result["items"]) == [0, 1, 2]
