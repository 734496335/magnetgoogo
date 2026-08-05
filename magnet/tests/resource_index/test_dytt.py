"""DYTT adapter and conservative multi-source movie automation tests."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from magnet.resource_index.acquisition.policy import LiveFetchPolicy
from magnet.resource_index.adapters.dytt.live_crawler import DyttLiveCrawler
from magnet.resource_index.adapters.dytt.parser import (
    decode_dytt_html,
    parse_latest_listing,
    parse_movie_detail,
)
from magnet.resource_index.adapters.movie_registry import (
    MovieSourceSpec,
    list_movie_sources,
)
from magnet.resource_index.adapters.registry import get_crawler_factory, list_sources
from magnet.resource_index.domain.movie_models import (
    MovieDetail,
    MovieListingCandidate,
    MovieResource,
)
from magnet.resource_index.errors import LIVE_HTTP_ERROR, LIVE_URL_REJECTED, NOT_FOUND, ResourceIndexError
from magnet.resource_index.pipeline.latest_crawl import (
    LatestCrawlPaths,
    run_deployment_doctor,
)
from magnet.resource_index.pipeline.movie_automation import (
    SafeMovieSourceResult,
    run_safe_movie_source,
)
from magnet.resource_index.pipeline.movie_latest import MovieLatestRunner, _qualified_publish_item
from magnet.resource_index.store.migrations import file_checksum
from magnet.resource_index.store.movie_source_state import MovieSourceStateStore
from magnet.resource_index.store.sqlite_repository import SqliteResourceRepository

NOW = datetime(2026, 7, 26, 0, 0, tzinfo=timezone.utc)

LISTING_HTML = """
<html><body>
<div class="co_content2"><a href="/i/old.html">旧推荐</a></div>
<table class="tbspan"><tr><td><b><a class="ulink" href="/i/122816.html"
title="2026年美国电影《后室》正片">后室</a></b></td></tr>
<tr><td><font>日期：2026-07-20 点击：3673</font></td></tr></table>
<table class="tbspan"><tr><td><b><a class="ulink" href="/i/122611.html"
title="2026年中国香港电影《功夫女足》TC国语v2">功夫女足</a></b></td></tr>
<tr><td><font>日期：2026-07-14 点击：17659</font></td></tr></table>
</body></html>
"""

DETAIL_HTML = """
<html><body><h1>2026年美国电影《后室》正片</h1>
<div id="Zoom"><img src="https://img.example/poster.jpg"><br>
◎译　　名　后室<br>◎片　　名　后室<br>◎年　　代　2026<br>
◎产　　地　美国<br>◎类　　别　科幻/恐怖<br>◎语　　言　英语<br>
◎上映日期　2026-07-20<br>◎豆瓣评分　7.2/10<br>
◎导　　演　凯恩·帕森斯<br>◎主　　演　切瓦特·埃加福<br>
　　　　　　雷娜特·赖因斯夫<br>◎简　　介<br>一段电影简介。
<div class="player_list"><a href="jianpian://pathtype=url&amp;path=https://video.example/a.m3u8">正片</a></div>
<a href="magnet:?xt=urn:btih:97430cd2a109439fc6e7da6b7ace7c4e6d53127c">1080p.HD中字</a>
</div><div id="downlist"><a href="1">1</a></div></body></html>
"""


def _candidate(rank: int) -> MovieListingCandidate:
    code = f"1228{rank:02d}"
    return MovieListingCandidate(
        rank=rank,
        detail_url=f"https://www.dytt8899.com/i/{code}.html",
        source_item_key=f"/i/{code}.html",
        content_code=code,
        listing_title=f"2026年美国电影《测试电影{rank}》HD中字",
        update_date=date(2026, 7, 20),
        recommended=False,
        highlight_labels=(),
        quality_tags=("HD", "中字"),
    )


def _detail(candidate: MovieListingCandidate, *, source_id: str = "dytt8899") -> MovieDetail:
    return MovieDetail(
        source_id=source_id,
        source_item_key=candidate.source_item_key,
        content_code=candidate.content_code,
        detail_url=candidate.detail_url,
        listing_title=candidate.listing_title,
        title=f"测试电影{candidate.rank}",
        original_title=None,
        year=2026,
        update_date=candidate.update_date,
        release_date=date(2026, 7, 20),
        duration_minutes=100,
        countries=("美国",),
        genres=("剧情",),
        languages=("英语",),
        directors=("导演",),
        actors=("演员",),
        imdb_id=None,
        douban_rating=7.0,
        douban_rating_text="7.0/10",
        douban_url=None,
        cover_source_url=f"https://img.example/{candidate.content_code}.jpg",
        synopsis="简介",
        recommended=False,
        highlight_labels=(),
        quality_tags=candidate.quality_tags,
        parser_version="dytt-parser/test",
        raw_document_hash="a" * 64,
        resources=(
            MovieResource(
                resource_type="player",
                provider="jianpian",
                resource_url=f"jianpian://movie/{candidate.content_code}",
                info_hash=None,
                display_title="正片",
                extraction_code=None,
                quality_tags=(),
            ),
        ),
    )


class _FakeCrawler:
    def __init__(
        self,
        candidates: list[MovieListingCandidate],
        calls: dict[str, int],
        *,
        source_id: str = "dytt8899",
    ) -> None:
        self.candidates = candidates
        self.calls = calls
        self.source_id = source_id
        self.http_requests = 0

    def crawl_latest_candidates(self, *, limit: int, max_listing_pages: int):
        self.calls["snapshot"] += 1
        self.http_requests += 1
        return self.candidates[:limit]

    def crawl_movie_detail(self, candidate: MovieListingCandidate):
        self.calls["detail"] += 1
        self.http_requests += 1
        return _detail(candidate, source_id=self.source_id)


class _Clock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value


def test_dytt_gb2312_meta_decodes_with_gb18030() -> None:
    raw = '<meta charset="gb2312"><title>电影天堂</title>'.encode("gb18030")
    assert "电影天堂" in decode_dytt_html(raw)


def test_dytt_listing_uses_only_latest_tables() -> None:
    items = parse_latest_listing(
        LISTING_HTML,
        page_url="https://www.dytt8899.com/html/gndy/dyzz/index.html",
    )
    assert len(items) == 2
    assert [item.rank for item in items] == [1, 2]
    assert items[0].listing_title == "2026年美国电影《后室》正片"
    assert items[0].update_date == date(2026, 7, 20)
    assert all("old" not in item.detail_url for item in items)


def test_dytt_detail_extracts_metadata_and_public_resources() -> None:
    candidate = parse_latest_listing(
        LISTING_HTML,
        page_url="https://www.dytt8899.com/html/gndy/dyzz/index.html",
    )[0]
    movie = parse_movie_detail(DETAIL_HTML, candidate=candidate)
    assert movie.title == "后室"
    assert movie.year == 2026
    assert movie.genres == ("科幻", "恐怖")
    assert movie.directors == ("凯恩·帕森斯",)
    assert movie.actors == ("切瓦特·埃加福", "雷娜特·赖因斯夫")
    assert movie.synopsis == "一段电影简介。"
    assert movie.cover_source_url == "https://img.example/poster.jpg"
    assert {(item.resource_type, item.provider) for item in movie.resources} == {
        ("player", "m3u8"),
        ("magnet", "magnet"),
    }
    player = next(item for item in movie.resources if item.resource_type == "player")
    assert player.resource_url == "https://video.example/a.m3u8"
    assert all(item.resource_url != "1" for item in movie.resources)


def test_dytt_crawler_maps_detail_404_to_not_found() -> None:
    class _NotFoundClient:
        def get(self, _url: str, **_kwargs):
            raise ResourceIndexError(LIVE_HTTP_ERROR, "HTTP status 404", {"status": 404})

    crawler = DyttLiveCrawler(
        policy=LiveFetchPolicy(
            enabled=True,
            acknowledged=True,
            max_pages=1,
            request_delay_seconds=15,
            concurrency=1,
        ),
        client=_NotFoundClient(),
    )
    with pytest.raises(ResourceIndexError) as exc:
        crawler.crawl_movie_detail(_candidate(1))
    assert exc.value.error_code == NOT_FOUND
    assert exc.value.context["status"] == 404


def test_dytt_qualified_publish_item_keeps_only_app_resources() -> None:
    item = {
        "title": "合格电影",
        "cover_source_url": "https://images.example/poster.jpg",
        "resources": [
            {"resource_type": "download", "provider": "ftp", "resource_url": "ftp://dead.example/a.mp4"},
            {"resource_type": "player", "provider": "m3u8", "resource_url": "https://video.example/a.m3u8"},
            {"resource_type": "magnet", "provider": "magnet", "resource_url": "magnet:?xt=urn:btih:" + "1" * 40},
            {"resource_type": "cloud", "provider": "quark", "resource_url": "https://pan.quark.cn/s/example"},
        ],
    }
    qualified, reason = _qualified_publish_item(item)
    assert reason is None
    assert qualified is not None
    assert [resource["resource_type"] for resource in qualified["resources"]] == ["magnet", "cloud"]

    missing, reason = _qualified_publish_item(
        {
            "title": "仅失效下载",
            "cover_source_url": "https://images.example/poster.jpg",
            "resources": item["resources"][:2],
        }
    )
    assert missing is None
    assert reason == "missing_publishable_resources"


def test_dytt_crawler_rejects_nonpublic_detail_path() -> None:
    crawler = DyttLiveCrawler(
        policy=LiveFetchPolicy(
            enabled=True,
            acknowledged=True,
            max_pages=1,
            request_delay_seconds=15,
            concurrency=1,
        )
    )
    invalid = MovieListingCandidate(
        rank=1,
        detail_url="https://www.dytt8899.com/e/data/private.html",
        source_item_key="/e/data/private.html",
        content_code="private",
        listing_title="private",
        update_date=None,
        recommended=False,
        highlight_labels=(),
        quality_tags=(),
    )
    with pytest.raises(ResourceIndexError) as exc:
        crawler.crawl_movie_detail(invalid)
    assert exc.value.error_code == LIVE_URL_REJECTED
    assert crawler.http_requests == 0


def test_movie_sources_are_not_exposed_through_the_legacy_crawler_protocol(
    tmp_path: Path,
) -> None:
    assert "dytt8899" not in list_sources()
    assert "sixv" not in list_sources()
    with pytest.raises(ResourceIndexError):
        get_crawler_factory("dytt8899")
    movie_sources = list_movie_sources()
    assert {"sixv", "dytt8899", "meijumi", "sixv-series"} <= set(movie_sources)
    assert movie_sources["sixv"]["catalog_role"] == "primary"
    assert movie_sources["sixv"]["metadata_priority"] == 300
    assert movie_sources["dytt8899"]["catalog_role"] == "supplemental"
    assert movie_sources["meijumi"]["catalog_role"] == "primary"
    assert movie_sources["sixv-series"]["catalog_role"] == "supplemental"
    report = run_deployment_doctor(
        output_dir=tmp_path / "doctor",
        db_path=tmp_path / "doctor" / "dytt.db",
        source_id="dytt8899",
    )
    assert report["status"] == "pass"
    assert report["checks"]["source_registry"]["source_kind"] == "movie_latest"


def test_generic_movie_runner_resumes_and_replays_zero_network(tmp_path: Path) -> None:
    paths = LatestCrawlPaths.for_output_dir(
        tmp_path / "out",
        source_id="dytt8899",
        target_count=2,
    )
    repo = SqliteResourceRepository(paths.db_path)
    candidates = [_candidate(1), _candidate(2)]
    calls = {"snapshot": 0, "detail": 0}
    runner = MovieLatestRunner(
        repo=repo,
        paths=paths,
        source_id="dytt8899",
        target_count=2,
        batch_size=1,
        snapshot_max_requests=1,
        batch_max_requests=1,
        max_listing_pages=1,
        crawler_builder=lambda _policy: _FakeCrawler(candidates, calls),
        snapshot_schema="movie-latest/dytt8899/1",
    )
    first = runner.run(refresh=True, max_batches=1)
    assert first.status == "pending"
    assert first.covered_count == 1
    assert first.snapshot_changed is True
    assert first.invocation_http_requests == 2
    second = runner.run(refresh=False)
    assert second.status == "success"
    assert second.invocation_http_requests == 1
    feed_hash = file_checksum(paths.feed_path)
    before = dict(calls)
    third = runner.run(refresh=False)
    assert third.status == "success"
    assert third.invocation_http_requests == 0
    assert calls == before
    assert file_checksum(paths.feed_path) == feed_hash
    feed = json.loads(paths.feed_path.read_text(encoding="utf-8"))
    assert [item["rank"] for item in feed["items"]] == [1, 2]
    repo.close()


def test_series_listing_progress_change_forces_one_detail_refresh(tmp_path: Path) -> None:
    paths = LatestCrawlPaths.for_output_dir(
        tmp_path / "out",
        source_id="sixv-series",
        target_count=1,
    )
    repo = SqliteResourceRepository(paths.db_path)
    calls = {"snapshot": 0, "detail": 0}
    candidates = [
        replace(
            _candidate(1),
            detail_url="https://www.6v520.com/dlz/2026-07-21/50027.html",
            source_item_key="/dlz/2026-07-21/50027.html",
            content_code="50027",
            listing_title="国产剧《江海潮生》更新09",
            update_date=date(2026, 7, 26),
            content_kind="series",
            series_title="江海潮生",
            episode_number=9,
            episode_label="更新09",
            update_status="更新09",
            brand_id="sixv",
            endpoint_origin="https://www.6v520.com",
        )
    ]
    runner = MovieLatestRunner(
        repo=repo,
        paths=paths,
        source_id="sixv-series",
        target_count=1,
        batch_size=1,
        snapshot_max_requests=1,
        batch_max_requests=1,
        max_listing_pages=1,
        crawler_builder=lambda _policy: _FakeCrawler(
            candidates,
            calls,
            source_id="sixv-series",
        ),
        snapshot_schema="media-latest/sixv-series/1",
    )

    first = runner.run(refresh=True)
    assert first.status == "success"
    assert calls == {"snapshot": 1, "detail": 1}

    candidates[0] = replace(
        candidates[0],
        listing_title="国产剧《江海潮生》更新11",
        update_date=date(2026, 7, 29),
        episode_number=11,
        episode_label="更新11",
        update_status="更新11",
    )
    second = runner.run(refresh=True)
    assert second.status == "success"
    assert calls == {"snapshot": 2, "detail": 2}
    stored = repo.conn.execute(
        "SELECT episode_number, episode_label, update_status FROM movie_items WHERE source_id = ?",
        ("sixv-series",),
    ).fetchone()
    assert tuple(stored) == (11, "更新11", "更新11")

    third = runner.run(refresh=True)
    assert third.status == "success"
    assert calls == {"snapshot": 3, "detail": 2}
    repo.close()


def test_existing_schema_0005_upgrades_without_movie_resource_loss(tmp_path: Path) -> None:
    db = tmp_path / "upgrade.db"
    sql_dir = Path(__file__).resolve().parents[2] / "resource_index" / "store" / "sql"
    connection = sqlite3.connect(db)
    for version in range(1, 6):
        path = next(sql_dir.glob(f"{version:04d}_*.sql"))
        connection.executescript(path.read_text(encoding="utf-8"))
        connection.execute(
            "INSERT OR REPLACE INTO schema_migrations(version, applied_at, checksum) VALUES (?, ?, ?)",
            (f"{version:04d}", "2026-07-26T00:00:00Z", file_checksum(path)),
        )
    connection.execute(
        """
        INSERT INTO movie_items(
            movie_id, source_id, source_item_key, detail_url, listing_title,
            title, countries_json, genres_json, languages_json, directors_json,
            actors_json, recommended, highlight_labels_json, quality_tags_json,
            parser_version, first_seen_at, last_seen_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, '[]', '[]', '[]', '[]', '[]', 0,
                  '[]', '[]', ?, ?, ?, ?, ?)
        """,
        (
            "movie:legacy",
            "sixv",
            "/dy/legacy.html",
            "https://www.6v520.com/dy/legacy.html",
            "Legacy Movie",
            "Legacy Movie",
            "sixv-parser/1",
            "2026-07-26T00:00:00Z",
            "2026-07-26T00:00:00Z",
            "2026-07-26T00:00:00Z",
            "2026-07-26T00:00:00Z",
        ),
    )
    connection.execute(
        """
        INSERT INTO movie_resources(
            resource_id, movie_id, resource_type, provider, resource_url,
            display_title, quality_tags_json, first_seen_at, last_seen_at,
            created_at, updated_at
        ) VALUES (?, ?, 'magnet', 'magnet', ?, ?, '[]', ?, ?, ?, ?)
        """,
        (
            "movie-resource:legacy",
            "movie:legacy",
            "magnet:?xt=urn:btih:97430cd2a109439fc6e7da6b7ace7c4e6d53127c",
            "Legacy Magnet",
            "2026-07-26T00:00:00Z",
            "2026-07-26T00:00:00Z",
            "2026-07-26T00:00:00Z",
            "2026-07-26T00:00:00Z",
        ),
    )
    connection.commit()
    connection.close()

    repo = SqliteResourceRepository(db)
    assert repo.init_schema() == "0008"
    assert repo.conn.execute("SELECT COUNT(*) FROM movie_items").fetchone()[0] == 1
    assert repo.conn.execute("SELECT COUNT(*) FROM movie_resources").fetchone()[0] == 1
    migrated = repo.conn.execute(
        "SELECT content_kind, series_title, brand_id, endpoint_origin FROM movie_items"
    ).fetchone()
    assert tuple(migrated) == ("movie", None, None, None)
    latest_columns = {
        row[1] for row in repo.conn.execute("PRAGMA table_info(latest_crawl_items)")
    }
    assert "source_item_key" in latest_columns
    tables = {
        row[0]
        for row in repo.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {
        "movie_cover_assets",
        "movie_external_resources",
        "movie_source_state",
    } <= tables
    repo.close()


def test_movie_source_state_interval_budget_refund_and_date_reset(tmp_path: Path) -> None:
    repo = SqliteResourceRepository(tmp_path / "state.db")
    assert repo.init_schema() == "0008"
    store = MovieSourceStateStore(repo)
    first = store.reserve(
        source_id="dytt8899",
        now=NOW,
        minimum_interval_hours=12,
        daily_budget=10,
        requested_requests=6,
    )
    assert first.allowed is True
    store.complete(
        source_id="dytt8899",
        now=NOW,
        reserved_requests=6,
        actual_requests=2,
        snapshot_hash="hash",
        success=True,
    )
    immediate = store.reserve(
        source_id="dytt8899",
        now=NOW + timedelta(hours=1),
        minimum_interval_hours=12,
        daily_budget=10,
        requested_requests=1,
    )
    assert immediate.allowed is False
    assert immediate.reason == "minimum_interval"
    later = store.reserve(
        source_id="dytt8899",
        now=NOW + timedelta(hours=13),
        minimum_interval_hours=12,
        daily_budget=10,
        requested_requests=8,
    )
    assert later.allowed is True
    exhausted = store.reserve(
        source_id="dytt8899-next",
        now=NOW,
        minimum_interval_hours=0,
        daily_budget=5,
        requested_requests=6,
    )
    assert exhausted.allowed is False
    assert exhausted.reason == "daily_budget"
    next_day = store.reserve(
        source_id="dytt8899",
        now=NOW + timedelta(days=1, hours=14),
        minimum_interval_hours=12,
        daily_budget=10,
        requested_requests=10,
    )
    assert next_day.allowed is True

    failed = store.reserve(
        source_id="dytt8899-failing",
        now=NOW,
        minimum_interval_hours=12,
        daily_budget=20,
        requested_requests=4,
    )
    assert failed.allowed is True
    store.complete(
        source_id="dytt8899-failing",
        now=NOW,
        reserved_requests=4,
        actual_requests=2,
        snapshot_hash=None,
        success=False,
    )
    backed_off = store.reserve(
        source_id="dytt8899-failing",
        now=NOW + timedelta(hours=13),
        minimum_interval_hours=12,
        daily_budget=20,
        requested_requests=1,
    )
    assert backed_off.allowed is False
    assert backed_off.reason == "failure_backoff"
    assert backed_off.next_due_at == "2026-07-27T00:00:00Z"
    after_backoff = store.reserve(
        source_id="dytt8899-failing",
        now=NOW + timedelta(hours=25),
        minimum_interval_hours=12,
        daily_budget=20,
        requested_requests=1,
    )
    assert after_backoff.allowed is True
    repo.close()


def test_safe_automation_charges_full_reservation_after_crash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from magnet.resource_index.adapters import movie_registry

    source_id = "test-movie-crash-budget"

    class _CrashCrawler:
        http_requests = 1

        def crawl_latest_candidates(self, *, limit: int, max_listing_pages: int):
            raise RuntimeError("transport channel lost")

        def crawl_movie_detail(self, candidate: MovieListingCandidate):
            raise AssertionError("detail should not run")

    spec = MovieSourceSpec(
        source_id=source_id,
        snapshot_schema="movie-latest/crash/1",
        default_count=2,
        minimum_delay_seconds=10,
        minimum_check_interval_hours=12,
        daily_request_budget=10,
        default_batch_size=1,
        automatic_max_batches=1,
        snapshot_max_requests=1,
        batch_max_requests=1,
        max_listing_pages=1,
        robots_url=None,
        allowed_origins=("https://www.dytt8899.com",),
        allowed_path_prefixes=("/i/",),
        crawler_factory=lambda _policy: _CrashCrawler(),
    )
    monkeypatch.setitem(movie_registry._SPECS, source_id, spec)
    with pytest.raises(RuntimeError, match="transport channel lost"):
        run_safe_movie_source(
            source_id=source_id,
            output_dir=tmp_path / "out",
            clock=lambda: NOW,
        )
    paths = LatestCrawlPaths.for_output_dir(
        tmp_path / "out",
        source_id=source_id,
        target_count=2,
    )
    repo = SqliteResourceRepository(paths.db_path)
    repo.init_schema()
    status = MovieSourceStateStore(repo).status(source_id=source_id, daily_budget=10)
    assert status["daily_reserved_requests"] == 2
    assert status["remaining_daily_requests"] == 8
    assert status["consecutive_failures"] == 1
    blocked = MovieSourceStateStore(repo).reserve(
        source_id=source_id,
        now=NOW + timedelta(hours=13),
        minimum_interval_hours=12,
        daily_budget=10,
        requested_requests=2,
    )
    assert blocked.allowed is False
    assert blocked.reason == "failure_backoff"
    allowed = MovieSourceStateStore(repo).reserve(
        source_id=source_id,
        now=NOW + timedelta(hours=25),
        minimum_interval_hours=12,
        daily_budget=10,
        requested_requests=2,
    )
    assert allowed.allowed is True
    repo.close()


def test_safe_automation_resumes_pending_snapshot_without_waiting_interval(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from magnet.resource_index.adapters import movie_registry

    source_id = "test-movie-safe"
    calls = {"snapshot": 0, "detail": 0}
    candidates = [_candidate(1), _candidate(2)]
    spec = MovieSourceSpec(
        source_id=source_id,
        snapshot_schema="movie-latest/test/1",
        default_count=2,
        minimum_delay_seconds=10,
        minimum_check_interval_hours=12,
        daily_request_budget=10,
        default_batch_size=1,
        automatic_max_batches=1,
        snapshot_max_requests=1,
        batch_max_requests=1,
        max_listing_pages=1,
        robots_url=None,
        allowed_origins=("https://www.dytt8899.com",),
        allowed_path_prefixes=("/i/",),
        crawler_factory=lambda _policy: _FakeCrawler(
            candidates,
            calls,
            source_id=source_id,
        ),
    )
    monkeypatch.setitem(movie_registry._SPECS, source_id, spec)
    clock = _Clock(NOW)
    first = run_safe_movie_source(
        source_id=source_id,
        output_dir=tmp_path / "out",
        clock=clock,
    )
    assert first.job_status == "pending"
    assert first.invocation_http_requests == 2
    assert calls == {"snapshot": 1, "detail": 1}
    clock.value = NOW + timedelta(hours=1)
    resumed = run_safe_movie_source(
        source_id=source_id,
        output_dir=tmp_path / "out",
        clock=clock,
    )
    assert resumed.job_status == "success"
    assert resumed.reason == "resume"
    assert calls == {"snapshot": 1, "detail": 2}
    clock.value = NOW + timedelta(hours=2)
    skipped = run_safe_movie_source(
        source_id=source_id,
        output_dir=tmp_path / "out",
        clock=clock,
    )
    assert skipped.status == "skipped"
    assert skipped.reason == "minimum_interval"
    assert calls == {"snapshot": 1, "detail": 2}
    clock.value = NOW + timedelta(hours=14)
    checked = run_safe_movie_source(
        source_id=source_id,
        output_dir=tmp_path / "out",
        clock=clock,
    )
    assert checked.job_status == "success"
    assert checked.snapshot_changed is False
    assert checked.invocation_http_requests == 1
    assert calls == {"snapshot": 2, "detail": 2}


def test_runner_does_not_retry_permanent_not_found_candidate(tmp_path: Path) -> None:
    paths = LatestCrawlPaths.for_output_dir(
        tmp_path / "out",
        source_id="dytt8899",
        target_count=2,
    )
    repo = SqliteResourceRepository(paths.db_path)
    candidates = [_candidate(1), _candidate(2)]
    calls = {"snapshot": 0, "detail": 0}

    class _NotFoundCrawler(_FakeCrawler):
        def crawl_movie_detail(self, candidate: MovieListingCandidate):
            self.calls["detail"] += 1
            self.http_requests += 1
            if candidate.rank == 1:
                raise ResourceIndexError(NOT_FOUND, "missing", {"status": 404})
            return _detail(candidate)

    runner = MovieLatestRunner(
        repo=repo,
        paths=paths,
        source_id="dytt8899",
        target_count=2,
        batch_size=2,
        max_attempts=3,
        snapshot_max_requests=1,
        batch_max_requests=2,
        max_listing_pages=1,
        crawler_builder=lambda _policy: _NotFoundCrawler(candidates, calls),
    )
    first = runner.run(refresh=True)
    assert first.status == "partial"
    row = repo.conn.execute(
        "SELECT status, attempts, last_error_code FROM latest_crawl_items WHERE job_id = ? AND rank = 1",
        (first.job_id,),
    ).fetchone()
    assert dict(row) == {"status": "failed", "attempts": 3, "last_error_code": NOT_FOUND}
    before = dict(calls)
    second = runner.run(refresh=False)
    assert second.status == "partial"
    assert second.invocation_http_requests == 0
    assert calls == before
    repo.close()


def test_runner_publishes_qualified_subset_from_larger_discovery_window(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from magnet.resource_index.adapters import movie_registry

    source_id = "test-qualified-window"
    candidates = [_candidate(1), _candidate(2), _candidate(3)]
    calls = {"snapshot": 0, "detail": 0}

    class _QualifiedCrawler(_FakeCrawler):
        def crawl_movie_detail(self, candidate: MovieListingCandidate):
            self.calls["detail"] += 1
            self.http_requests += 1
            detail = _detail(candidate, source_id=source_id)
            if candidate.rank == 1:
                return detail
            resource = MovieResource(
                resource_type="magnet",
                provider="magnet",
                resource_url=f"magnet:?xt=urn:btih:{candidate.rank:040x}",
                info_hash=f"{candidate.rank:040x}",
                display_title=f"测试电影{candidate.rank}",
                extraction_code=None,
                quality_tags=(),
            )
            return replace(detail, resources=(resource,))

    spec = MovieSourceSpec(
        source_id=source_id,
        snapshot_schema="movie-latest/qualified/1",
        default_count=3,
        minimum_delay_seconds=0,
        minimum_check_interval_hours=0,
        daily_request_budget=10,
        default_batch_size=3,
        automatic_max_batches=1,
        snapshot_max_requests=1,
        batch_max_requests=3,
        max_listing_pages=1,
        robots_url=None,
        allowed_origins=("https://www.dytt8899.com",),
        allowed_path_prefixes=("/i/",),
        crawler_factory=lambda _policy: _QualifiedCrawler(candidates, calls, source_id=source_id),
        publish_count=2,
    )
    monkeypatch.setitem(movie_registry._SPECS, source_id, spec)
    paths = LatestCrawlPaths.for_output_dir(tmp_path / "out", source_id=source_id, target_count=3)
    repo = SqliteResourceRepository(paths.db_path)
    runner = MovieLatestRunner(
        repo=repo,
        paths=paths,
        source_id=source_id,
        target_count=3,
        batch_size=3,
        snapshot_max_requests=1,
        batch_max_requests=3,
        max_listing_pages=1,
        crawler_builder=lambda _policy: _QualifiedCrawler(candidates, calls, source_id=source_id),
    )
    result = runner.run(refresh=True)
    assert result.status == "success"
    assert result.covered_count == 3
    assert result.movie_count == 2
    payload = json.loads(paths.feed_path.read_text(encoding="utf-8"))
    assert [item["rank"] for item in payload["items"]] == [1, 2]
    assert payload["summary"]["target_count"] == 2
    assert payload["summary"]["discovery_target_count"] == 3
    assert payload["summary"]["disqualified_counts"] == {
        "missing_title": 0,
        "missing_cover": 0,
        "missing_publishable_resources": 1,
    }
    assert all(resource["resource_type"] == "magnet" for item in payload["items"] for resource in item["resources"])
    repo.close()


def test_generic_runner_rejects_candidate_outside_registered_boundary(tmp_path: Path) -> None:
    paths = LatestCrawlPaths.for_output_dir(
        tmp_path / "out",
        source_id="dytt8899",
        target_count=2,
    )
    repo = SqliteResourceRepository(paths.db_path)
    calls = {"snapshot": 0, "detail": 0}
    candidates = [
        replace(
            _candidate(1),
            detail_url="https://example.com/i/122801.html",
            source_item_key="/i/122801.html",
        ),
        _candidate(2),
    ]
    runner = MovieLatestRunner(
        repo=repo,
        paths=paths,
        source_id="dytt8899",
        target_count=2,
        batch_size=1,
        snapshot_max_requests=1,
        batch_max_requests=1,
        max_listing_pages=1,
        crawler_builder=lambda _policy: _FakeCrawler(candidates, calls),
    )
    with pytest.raises(ResourceIndexError) as exc:
        runner.run(refresh=True, max_batches=0)
    assert exc.value.error_code == LIVE_URL_REJECTED
    assert calls == {"snapshot": 1, "detail": 0}
    assert not paths.snapshot_path.exists()
    repo.close()


def test_safe_cli_continues_after_one_source_fails(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import magnet.resource_index.cli as cli_module

    calls: list[str] = []

    def fake_run(*, source_id: str, output_dir: str, target_count: int | None, logger):
        calls.append(source_id)
        if source_id == "broken-source":
            raise ValueError("broken source")
        return SafeMovieSourceResult(
            source_id=source_id,
            status="ran",
            reason="scheduled_check",
            target_count=2,
            invocation_http_requests=1,
            reserved_requests=2,
            snapshot_changed=False,
            job_status="success",
            covered_count=2,
            remaining_daily_requests=8,
            db_path="movie.db",
            feed_path="movie_feed.json",
        )

    monkeypatch.setattr(cli_module, "run_safe_movie_source", fake_run)
    monkeypatch.setattr(cli_module, "setup_logging", lambda *_args, **_kwargs: None)
    args = SimpleNamespace(
        yes=True,
        source=["broken-source", "healthy-source"],
        log=None,
        output_dir="data/resource_index",
        count=None,
    )
    code = cli_module.cmd_crawl_movies_safe(args)
    output = json.loads(capsys.readouterr().out)
    assert code == 1
    assert calls == ["broken-source", "healthy-source"]
    assert output[0]["status"] == "error"
    assert output[1]["status"] == "ran"
