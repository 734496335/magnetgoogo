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
    cover_url: str | None = "https://covers.example/default.jpg",
    synopsis: str | None = None,
) -> dict:
    resource_url = resource
    info_hash = resource.rsplit(":", 1)[-1].split("&", 1)[0]
    if kind == "series" and season is not None and "&dn=" not in resource_url:
        resource_url += f"&dn=Fixture.S{season:02d}E{(episode or 1):02d}.1080p"
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
        "cover_source_url": cover_url,
        "synopsis": synopsis,
        "recommended": False,
        "highlight_labels": [],
        "quality_tags": [],
        "resources": [
            {
                "resource_type": "magnet",
                "provider": "magnet",
                "url": resource_url,
                "info_hash": info_hash,
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


def test_aggregate_requires_title_cover_and_resource_but_not_rating(tmp_path: Path) -> None:
    feed = tmp_path / "required.json"
    valid = _item(
        source_id="sixv",
        brand_id="sixv",
        title="有封面的电影",
        year=2026,
        resource="magnet:?xt=urn:btih:AAA",
    )
    missing_cover = _item(
        source_id="dytt8899",
        brand_id="dytt8899",
        title="缺封面的电影",
        year=2026,
        resource="magnet:?xt=urn:btih:BBB",
        cover_url=None,
    )
    _write_feed(feed, "mixed", [valid, missing_cover])

    result = aggregate_media_feeds([feed])

    assert result["summary"]["record_count"] == 1
    assert result["items"][0]["title"] == "有封面的电影"
    assert result["items"][0]["douban_rating"] is None
    assert result["summary"]["dropped_missing_cover_count"] == 1
    assert result["summary"]["dropped_missing_title_count"] == 0
    assert result["summary"]["dropped_zero_resource_count"] == 0


def test_aggregate_uses_source_priority_for_title_cover_and_synopsis(tmp_path: Path) -> None:
    sixv = tmp_path / "sixv-priority.json"
    dytt = tmp_path / "dytt-priority.json"
    primary = _item(
        source_id="sixv",
        brand_id="sixv",
        title="寒战 1994",
        year=2026,
        update_date="2026-07-20",
        resource="magnet:?xt=urn:btih:AAA",
        cover_url="https://sixv.example/cover.jpg",
        synopsis="SixV简介",
    )
    supplemental = _item(
        source_id="dytt8899",
        brand_id="dytt8899",
        title="寒战1994",
        year=2026,
        update_date="2026-07-30",
        resource="magnet:?xt=urn:btih:BBB",
        cover_url="https://dytt.example/cover.jpg",
        synopsis="DYTT简介",
    )
    supplemental["actors"] = ["演员甲", "演员乙"]
    _write_feed(sixv, "sixv", [primary])
    _write_feed(dytt, "dytt8899", [supplemental])

    result = aggregate_media_feeds([dytt, sixv])
    merged = result["items"][0]

    assert merged["primary_source_id"] == "sixv"
    assert merged["title"] == "寒战 1994"
    assert merged["cover_source_url"] == "https://sixv.example/cover.jpg"
    assert merged["synopsis"] == "SixV简介"
    assert len(merged["resources"]) == 2
    assert merged["actors"] == ["演员甲", "演员乙"]


def test_aggregate_primary_source_can_borrow_missing_cover_from_supplement(tmp_path: Path) -> None:
    sixv = tmp_path / "sixv-no-cover.json"
    dytt = tmp_path / "dytt-cover.json"
    _write_feed(
        sixv,
        "sixv",
        [
            _item(
                source_id="sixv",
                brand_id="sixv",
                title="互补电影",
                year=2026,
                resource="magnet:?xt=urn:btih:AAA",
                cover_url=None,
            )
        ],
    )
    _write_feed(
        dytt,
        "dytt8899",
        [
            _item(
                source_id="dytt8899",
                brand_id="dytt8899",
                title="互补电影",
                year=2026,
                resource="magnet:?xt=urn:btih:BBB",
                cover_url="https://dytt.example/fallback.jpg",
            )
        ],
    )

    result = aggregate_media_feeds([sixv, dytt])
    merged = result["items"][0]

    assert merged["primary_source_id"] == "sixv"
    assert merged["cover_source_url"] == "https://dytt.example/fallback.jpg"
    assert len(merged["resources"]) == 2


def test_aggregate_quarantines_cross_media_duplicate_resources(tmp_path: Path) -> None:
    feed = tmp_path / "movies.json"
    first = _item(
        source_id="movie-a",
        brand_id="sixv",
        title="电影甲",
        year=2026,
        resource="magnet:?xt=urn:btih:AAA",
    )
    second = _item(
        source_id="movie-b",
        brand_id="sixv",
        title="电影乙",
        year=2026,
        resource="magnet:?xt=urn:btih:BBB",
    )
    duplicate = {
        "resource_type": "cloud",
        "provider": "baidu",
        "url": "https://pan.baidu.com/s/shared?pwd=test",
        "info_hash": None,
        "display_title": "shared",
        "extraction_code": "test",
        "quality_tags": [],
    }
    first["resources"].append(dict(duplicate))
    second["resources"].append(dict(duplicate))
    _write_feed(feed, "sixv", [first, second])

    result = aggregate_media_feeds([feed])

    assert result["summary"]["record_count"] == 2
    assert result["summary"]["resource_count"] == 2
    assert result["summary"]["quarantined_resource_count"] == 2
    assert result["summary"]["quarantine_reason_counts"]["cross_media_duplicate"] == 2
    assert all(
        resource["provider"] == "magnet"
        for item in result["items"]
        for resource in item["resources"]
    )


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
    assert all(resource["season_number"] == 19 for resource in merged["resources"])
    assert result["summary"]["quarantine_reason_counts"].get("season_unknown", 0) == 0


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


def test_xmen_explicit_second_season_partitions_first_and_inherits_unknown_resources(tmp_path: Path) -> None:
    feed = tmp_path / "xmen.json"
    xmen = _item(
        source_id="meijumi",
        brand_id="meijumi",
        title="X战警97 第一季",
        year=2026,
        kind="series",
        season=2,
        episode=6,
        resource=(
            "magnet:?xt=urn:btih:S02"
            "&dn=X-Men%2097%20S02E03%20Rise%20of%20Apocalypse%201080p"
        ),
    )
    xmen["series_title"] = "X战警97 第一至二季"
    xmen["resources"].extend(
        [
            {
                "resource_type": "magnet",
                "provider": "magnet",
                "url": "magnet:?xt=urn:btih:S01&dn=X-Men%2097%20S01E04%201080p",
                "info_hash": "S01",
                "display_title": "1080P",
                "extraction_code": None,
                "quality_tags": ["1080p"],
            },
            {
                "resource_type": "cloud",
                "provider": "quark",
                "url": "https://pan.quark.cn/s/unknown-season",
                "info_hash": None,
                "display_title": "夸克盘",
                "extraction_code": None,
                "quality_tags": [],
            },
        ]
    )
    _write_feed(feed, "meijumi", [xmen])

    quarantine_path = tmp_path / "quarantine.json"
    quality_path = tmp_path / "quality.json"
    result = aggregate_media_feeds(
        [feed],
        quarantine_output_path=quarantine_path,
        quality_output_path=quality_path,
    )

    assert result["summary"]["record_count"] == 2
    by_season = {item["season_number"]: item for item in result["items"]}
    assert set(by_season) == {1, 2}
    assert by_season[1]["title"] == "X战警97 第一季"
    assert len(by_season[1]["resources"]) == 1
    assert by_season[1]["resources"][0]["episode_label"] == "S01E04"
    item = by_season[2]
    assert item["title"] == "X战警97 第二季"
    assert item["series_title"] == "X战警97"
    assert len(item["resources"]) == 2
    assert {resource["season_number"] for resource in item["resources"]} == {2}
    assert any(resource["episode_label"] == "S02E03" for resource in item["resources"])
    assert any(resource["provider"] == "quark" for resource in item["resources"])
    assert result["quality"]["accepted_cross_season_count"] == 0
    assert result["quality"]["weak_episode_title_count"] == 0
    quarantine = json.loads(quarantine_path.read_text(encoding="utf-8"))
    assert quarantine["reason_counts"] == {}
    assert json.loads(quality_path.read_text(encoding="utf-8"))["status"] == "pass"


def test_unscoped_multiseason_page_splits_into_season_entries(tmp_path: Path) -> None:
    feed = tmp_path / "multi-season.json"
    item = _item(
        source_id="source",
        brand_id="source",
        title="同一剧集",
        year=2026,
        kind="series",
        season=None,
        episode=None,
        resource="magnet:?xt=urn:btih:S01&dn=Show%20S01E01%201080p",
    )
    item["resources"].append(
        {
            "resource_type": "magnet",
            "provider": "magnet",
            "url": "magnet:?xt=urn:btih:S02&dn=Show%20S02E01%201080p",
            "info_hash": "S02",
            "display_title": "1080P",
            "extraction_code": None,
            "quality_tags": ["1080p"],
        }
    )
    _write_feed(feed, "source", [item])

    result = aggregate_media_feeds([feed])
    assert result["summary"]["record_count"] == 2
    assert {entry["season_number"] for entry in result["items"]} == {1, 2}
    assert {entry["title"] for entry in result["items"]} == {"同一剧集 第一季", "同一剧集 第二季"}
    assert all(len(entry["resources"]) == 1 for entry in result["items"])


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
