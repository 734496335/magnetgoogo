"""6V movie source parsing, persistence and resumable-runner tests."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from magnet.resource_index.adapters.movie_registry import get_movie_source
from magnet.resource_index.adapters.sixv.models import (
    SixVListingCandidate,
    SixVMovieDetail,
    SixVMovieResource,
)
from magnet.resource_index.adapters.sixv.parser import (
    decode_sixv_html,
    normalize_movie_genres,
    normalize_movie_title,
    parse_latest_listing,
    parse_movie_detail,
)
from magnet.resource_index.errors import DETAIL_DOM_DRIFT, LIVE_RATE_LIMITED, ResourceIndexError
from magnet.resource_index.pipeline.latest_crawl import LatestCrawlPaths, read_latest_status
from magnet.resource_index.pipeline.sixv_latest import SixVLatestRunner
from magnet.resource_index.store.movie_repository import MovieRepository
from magnet.resource_index.store.sqlite_repository import SqliteResourceRepository

NOW = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)


def test_sixv_source_snapshot_window_can_cover_default_catalog() -> None:
    spec = get_movie_source("sixv")
    assert spec.default_count == 100
    assert spec.max_listing_pages == 5
    assert spec.snapshot_max_requests >= spec.max_listing_pages


def test_detail_parser_reports_dom_drift_with_stable_error_code() -> None:
    with pytest.raises(ResourceIndexError) as exc_info:
        parse_movie_detail("<html><body>unexpected</body></html>", candidate=_candidate(1))
    assert exc_info.value.error_code == DETAIL_DOM_DRIFT
    assert exc_info.value.context["selector"] == "#endText"


def test_movie_title_normalization_removes_listing_noise() -> None:
    assert normalize_movie_title(
        "2026科幻惊悚《揭秘日》1080p.HD中英双字",
        "2026科幻惊悚《揭秘日》1080p.HD中英双字",
    ) == "揭秘日"
    assert normalize_movie_title("宇宙巨人:希曼崛起") == "宇宙巨人：希曼崛起"
    assert normalize_movie_title("末日逃生2:迁移") == "末日逃生2：迁移"
    assert normalize_movie_title("WWE: Unreal") == "WWE: Unreal"
    assert normalize_movie_genres(("纪录", "片", "运动")) == ("纪录片", "运动")


LISTING_HTML = """
<html><body><div id="main"><ul class="list">
<li><span>2026-07-25</span><a href="/dy/2026-07-24/50051.html"><font color="#FF0000">2026动作剧情《寒战1994》4K.HD中字</font></a></li>
<li><span>2026-07-24</span><a href="/dy/2026-07-24/50050.html">2026动作科幻《群体》1080p.HD中字</a></li>
</ul></div></body></html>
"""

DETAIL_HTML = """
<html><body><h1>2026动作剧情《寒战1994》4K.HD中字</h1>
<div id="endText">
<div>◎标　　题　寒战1994</div>
<div>◎译　　名　寒战前传 / Cold War 1994</div>
<div>◎片　　名　寒戰1994</div>
<div>◎年　　代　2026</div>
<div>◎产　　地　中国香港 / 中国大陆</div>
<div>◎类　　别　剧情 / 动作 / 犯罪</div>
<div>◎语　　言　粤语 / 汉语普通话</div>
<div>◎上映日期　2026-05-01(中国大陆)</div>
<div>◎IMDb链接　tt36576750</div>
<div>◎豆瓣评分　7.1/10 (98748人评价)</div>
<div>◎豆瓣链接　https://movie.douban.com/subject/36857924/</div>
<div>◎片　　长　117分钟</div>
<div>◎导　　演　梁乐民</div>
<div>◎演　　员　吴彦祖</div><div>刘俊谦</div>
<div>◎简　　介</div><div>一段电影简介。</div>
<p><img src="https://img.example/poster.jpg" /></p>
<hr />
<a href="magnet:?xt=urn:btih:97430cd2a109439fc6e7da6b7ace7c4e6d53127c">2160p.HD中字.mkv</a>
<p>夸克云盘链接：<a href="https://pan.quark.cn/s/abc">https://pan.quark.cn/s/abc</a><br />
百度云盘链接：<a href="https://pan.baidu.com/s/xyz?pwd=dyg7">https://pan.baidu.com/s/xyz?pwd=dyg7</a> 提取码: dyg7</p>
</div></body></html>
"""

PARAGRAPH_DETAIL_HTML = """
<html><body><h1>2026动作科幻《群体》1080p.HD中字</h1>
<div id="endText">
<p><img src="https://img.example/group.jpg" /></p>
<p>◎中 文 名: 群体</p>
<p>◎译　　名: Colony</p>
<p>◎年　　代: 2026</p>
<p>◎产　　地: 韩国</p>
<p>◎类　　别: 动作 / 科幻 / 悬疑 / 惊悚 片\"> 惊悚</p>
<p>◎语　　言: 韩语</p>
<p>◎上映日期: 2026-05-21(韩国)</p>
<p>◎IMDb链接: tt34385135</p>
<p>◎豆瓣评分: 6.4 / 10</p>
<p>◎片　　长: 122分钟</p>
<p>◎导　　演: 延尚昊</p>
<p>◎主　　演: 全智贤</p>
<p>具教焕</p>
<p>◎简　　介</p>
<p>影片讲述幸存者对抗感染者的故事。</p>
<hr />
<a href="magnet:?xt=urn:btih:1111111111111111111111111111111111111111">1080p.HD中字.mp4</a>
</div></body></html>
"""


def _candidate(rank: int, *, recommended: bool = False) -> SixVListingCandidate:
    code = f"5005{rank}"
    return SixVListingCandidate(
        rank=rank,
        detail_url=f"https://www.6v520.com/dy/2026-07-24/{code}.html",
        source_item_key=f"/dy/2026-07-24/{code}.html",
        content_code=code,
        listing_title=f"2026动作《测试电影{rank}》1080p.HD中字",
        update_date=date(2026, 7, 25),
        recommended=recommended,
        highlight_labels=("推荐",) if recommended else (),
        quality_tags=("1080p", "HD", "中字"),
    )


def _detail(candidate: SixVListingCandidate) -> SixVMovieDetail:
    return SixVMovieDetail(
        source_id="sixv",
        source_item_key=candidate.source_item_key,
        content_code=candidate.content_code,
        detail_url=candidate.detail_url,
        listing_title=candidate.listing_title,
        title=f"测试电影{candidate.rank}",
        original_title=None,
        year=2026,
        update_date=candidate.update_date,
        release_date=date(2026, 7, 1),
        duration_minutes=100,
        countries=("中国大陆",),
        genres=("动作",),
        languages=("汉语普通话",),
        directors=("导演",),
        actors=("演员",),
        imdb_id=None,
        douban_rating=7.0,
        douban_rating_text="7.0/10",
        douban_url=None,
        cover_source_url=f"https://img.example/{candidate.content_code}.jpg",
        synopsis="简介",
        recommended=candidate.recommended,
        highlight_labels=candidate.highlight_labels,
        quality_tags=candidate.quality_tags,
        parser_version="sixv-parser/1.0.0",
        raw_document_hash="a" * 64,
        resources=(
            SixVMovieResource(
                resource_type="magnet",
                provider="magnet",
                resource_url=f"magnet:?xt=urn:btih:{candidate.content_code.zfill(40)}",
                info_hash=candidate.content_code.zfill(40),
                display_title="1080p.HD中字.mkv",
                extraction_code=None,
                quality_tags=("1080p", "HD", "中字"),
            ),
        ),
    )


def test_gb2312_meta_is_decoded_with_gb18030() -> None:
    raw = '<meta charset="gb2312"><title>最新电影</title>'.encode("gb18030")
    assert "最新电影" in decode_sixv_html(raw)


def test_listing_parser_preserves_red_recommendation() -> None:
    items = parse_latest_listing(
        LISTING_HTML,
        page_url="https://www.6v520.com/dy/",
    )
    assert len(items) == 2
    assert items[0].recommended is True
    assert items[0].highlight_labels == ("推荐",)
    assert items[0].quality_tags == ("4K", "HD", "中字")
    assert items[1].recommended is False
    assert items[1].rank == 2


def test_listing_parser_accepts_registered_mirror_host_without_allowing_cross_origin_links() -> None:
    mirror_items = parse_latest_listing(
        LISTING_HTML,
        page_url="https://www.6v520.net/dy/",
    )
    assert len(mirror_items) == 2
    assert mirror_items[0].detail_url.startswith("https://www.6v520.net/")

    hostile = """
    <html><body><div id="main"><ul class="list">
    <li><span>2026-08-14</span><a href="https://evil.example/12345.html">外部伪造条目</a></li>
    </ul></div></body></html>
    """
    assert parse_latest_listing(hostile, page_url="https://www.6v520.net/dy/") == []


def test_detail_parser_extracts_movie_and_download_resources() -> None:
    candidate = parse_latest_listing(
        LISTING_HTML,
        page_url="https://www.6v520.com/dy/",
    )[0]
    movie = parse_movie_detail(DETAIL_HTML, candidate=candidate)
    assert movie.title == "寒战1994"
    assert movie.original_title == "寒戰1994"
    assert movie.release_date == date(2026, 5, 1)
    assert movie.duration_minutes == 117
    assert movie.genres == ("剧情", "动作", "犯罪")
    assert movie.directors == ("梁乐民",)
    assert movie.actors == ("吴彦祖", "刘俊谦")
    assert movie.recommended is True
    assert movie.cover_source_url == "https://img.example/poster.jpg"
    assert len(movie.resources) == 3
    providers = {resource.provider: resource for resource in movie.resources}
    assert providers["quark"].extraction_code is None
    assert providers["baidu"].extraction_code == "dyg7"
    assert providers["magnet"].info_hash == "97430cd2a109439fc6e7da6b7ace7c4e6d53127c"


def test_detail_parser_supports_paragraph_template_and_alias_labels() -> None:
    movie = parse_movie_detail(
        PARAGRAPH_DETAIL_HTML,
        candidate=_candidate(1),
    )
    assert movie.title == "群体"
    assert movie.original_title == "Colony"
    assert movie.genres == ("动作", "科幻", "悬疑", "惊悚")
    assert movie.languages == ("韩语",)
    assert movie.directors == ("延尚昊",)
    assert movie.actors == ("全智贤", "具教焕")
    assert movie.synopsis == "影片讲述幸存者对抗感染者的故事。"


def test_detail_parser_falls_back_to_listing_year_when_metadata_omits_year() -> None:
    html = """
    <html><body><h1>2026科幻惊悚《灵魂伴侣》1080p.HD中英双字</h1>
    <div id="endText">
      <p><img src="https://img.example/soulmate.jpg" /></p>
      <p>◎标　　题　灵魂伴侣</p>
      <hr />
      <a href="magnet:?xt=urn:btih:3333333333333333333333333333333333333333">1080p.HD中英双字.mp4</a>
    </div></body></html>
    """
    candidate = replace(
        _candidate(1),
        listing_title="2026科幻惊悚《灵魂伴侣》1080p.HD中英双字",
    )
    movie = parse_movie_detail(html, candidate=candidate)
    assert movie.year == 2026
    assert movie.parser_version == "sixv-parser/1.0.1"


@pytest.mark.parametrize(
    ("source_id", "minimum_items"),
    (
        ("sixv", 30),
        ("dytt8899", 50),
        ("meijumi", 50),
        ("sixv-series", 50),
    ),
)
def test_daily_source_budget_can_absorb_multi_day_update_bursts(
    source_id: str,
    minimum_items: int,
) -> None:
    spec = get_movie_source(source_id)
    assert spec.default_batch_size * spec.automatic_max_batches >= minimum_items
    reserved = spec.snapshot_max_requests + spec.automatic_max_batches * spec.batch_max_requests
    assert reserved <= spec.daily_request_budget


def test_detail_parser_splits_compact_multifield_paragraph() -> None:
    html = """
    <html><body><h1>列表标题</h1><div id="endText">
    <p>
      ◎标　　题　潜伏者<br />
      ◎片　　名　Lurker<br />
      ◎年　　代　2025<br />
      ◎产　　地　<a>美国</a> / <a>意大利</a><br />
      ◎类　　别　<a>剧情</a> / <a>惊悚</a><span>片\"></span><a>惊悚</a> / 犯罪<br />
      ◎语　　言　英语<br />
      ◎导　　演　亚历克斯·罗素<br />
      ◎演　　员　西奥多·佩尔兰<br />阿奇·马德基
    </p>
    <p>◎简　　介<br />一段简介。</p>
    <hr /><a href="magnet:?xt=urn:btih:2222222222222222222222222222222222222222">1080p</a>
    </div></body></html>
    """
    movie = parse_movie_detail(html, candidate=_candidate(1))
    assert movie.title == "潜伏者"
    assert movie.original_title == "Lurker"
    assert movie.countries == ("美国", "意大利")
    assert movie.genres == ("剧情", "惊悚", "犯罪")
    assert movie.directors == ("亚历克斯·罗素",)
    assert movie.actors == ("西奥多·佩尔兰", "阿奇·马德基")
    assert movie.synopsis == "一段简介。"


def test_detail_parser_stops_synopsis_before_download_and_footer_sections() -> None:
    html = """
    <html><body><h1>美剧《示例剧》第一季全</h1><div id="endText">
      <p>◎标　　题　示例剧</p>
      <p>◎年　　代　2023</p>
      <p>◎简　　介</p>
      <p>这是一段应当保留的剧情简介。</p>
      <p>【下载地址】</p>
      <p><a href="magnet:?xt=urn:btih:4444444444444444444444444444444444444444">磁力：S01全集</a></p>
      <div class="tps">上一篇 旧剧 下一篇 新剧</div>
      <div class="tps">下载帮助：本站所有资源完全免费。</div>
      <div class="downtps">示例剧网友评论：</div>
    </div></body></html>
    """
    movie = parse_movie_detail(html, candidate=_candidate(1))
    assert movie.synopsis == "这是一段应当保留的剧情简介。"
    assert len(movie.resources) == 1


def test_detail_parser_truncates_inline_download_marker_from_synopsis() -> None:
    html = """
    <html><body><h1>列表标题</h1><div id="endText">
      <p>◎标　　题　内联标志示例</p>
      <p>◎简　　介</p>
      <p>真实简介内容。 【下载地址】 磁力：不应进入简介</p>
      <a href="magnet:?xt=urn:btih:5555555555555555555555555555555555555555">1080p</a>
    </div></body></html>
    """
    movie = parse_movie_detail(html, candidate=_candidate(1))
    assert movie.synopsis == "真实简介内容。"
    assert len(movie.resources) == 1


def test_detail_parser_falls_back_to_listing_genres_when_source_omits_category() -> None:
    html = """
    <html><body><h1>2026剧情《天空依旧》1080p.HD国语中字</h1>
    <div id="endText">
      <p>◎标　　题　天空依旧</p>
      <p>◎年　　代　2026</p>
      <p>◎简　　介</p><p>一段简介。</p>
      <hr /><a href="magnet:?xt=urn:btih:3333333333333333333333333333333333333333">1080p</a>
    </div></body></html>
    """
    candidate = replace(
        _candidate(1),
        listing_title="2026剧情《天空依旧》1080p.HD国语中字",
    )
    movie = parse_movie_detail(html, candidate=candidate)
    assert movie.genres == ("剧情",)


def test_schema_0007_adds_media_brand_identity(tmp_path: Path) -> None:
    repo = SqliteResourceRepository(tmp_path / "movie.db")
    assert repo.init_schema() == "0008"
    tables = {
        row[0]
        for row in repo.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {
        "movie_items",
        "movie_resources",
        "movie_cover_assets",
        "movie_external_resources",
        "movie_source_state",
    } <= tables
    columns = {
        row[1]
        for row in repo.conn.execute("PRAGMA table_info(movie_items)")
    }
    assert {
        "content_kind",
        "series_title",
        "brand_id",
        "endpoint_origin",
        "rotten_tomatoes_rating",
        "rotten_tomatoes_rating_text",
        "rotten_tomatoes_url",
        "bangumi_rating",
        "bangumi_rating_text",
        "bangumi_subject_id",
        "bangumi_url",
    } <= columns
    repo.close()


def test_external_rating_placeholders_survive_null_crawler_updates(tmp_path: Path) -> None:
    repo = SqliteResourceRepository(tmp_path / "ratings.db")
    assert repo.init_schema() == "0008"
    store = MovieRepository(repo)
    candidate = _candidate(1)
    rated = replace(
        _detail(candidate),
        rotten_tomatoes_rating=86,
        rotten_tomatoes_rating_text="86%",
        rotten_tomatoes_url="https://www.rottentomatoes.com/m/test_movie",
        bangumi_rating=7.8,
        bangumi_rating_text="7.8/10",
        bangumi_subject_id="123456",
        bangumi_url="https://bgm.tv/subject/123456",
    )
    store.upsert(rated, now=NOW)
    store.upsert(_detail(candidate), now=NOW)

    item = store.feed_item(
        source_id="sixv",
        detail_url=candidate.detail_url,
        rank=1,
        source_item_key=candidate.source_item_key,
    )
    assert item is not None
    assert item["rotten_tomatoes_rating"] == 86
    assert item["rotten_tomatoes_rating_text"] == "86%"
    assert item["rotten_tomatoes_url"].endswith("/m/test_movie")
    assert item["bangumi_rating"] == 7.8
    assert item["bangumi_rating_text"] == "7.8/10"
    assert item["bangumi_subject_id"] == "123456"
    assert item["bangumi_url"].endswith("/subject/123456")
    repo.close()


def test_movie_repository_is_idempotent_and_updates_recommendation(tmp_path: Path) -> None:
    repo = SqliteResourceRepository(tmp_path / "movie.db")
    repo.init_schema()
    store = MovieRepository(repo)
    candidate = _candidate(1, recommended=True)
    first = store.upsert(_detail(candidate), now=NOW)
    second_candidate = _candidate(1, recommended=False)
    second = store.upsert(_detail(second_candidate), now=NOW)
    assert first.movie_created is True
    assert first.resources_created == 1
    assert second.movie_updated is True
    assert second.resources_updated == 1
    assert store.counts(source_id="sixv") == {
        "movies": 1,
        "resources": 1,
        "recommended": 0,
    }
    repo.close()


class _FakeCrawler:
    def __init__(self, candidates: list[SixVListingCandidate], calls: dict[str, int]) -> None:
        self.candidates = candidates
        self.calls = calls
        self.http_requests = 0

    def crawl_latest_candidates(self, *, limit: int, max_listing_pages: int):
        self.calls["snapshot"] += 1
        self.http_requests += 1
        return self.candidates[:limit]

    def crawl_movie_detail(self, candidate: SixVListingCandidate):
        self.calls["detail"] += 1
        self.http_requests += 1
        return _detail(candidate)


def test_sixv_runner_resumes_and_completed_rerun_is_zero_network(tmp_path: Path) -> None:
    paths = LatestCrawlPaths.for_output_dir(
        tmp_path / "out",
        source_id="sixv",
        target_count=2,
    )
    repo = SqliteResourceRepository(paths.db_path)
    calls = {"snapshot": 0, "detail": 0}
    candidates = [_candidate(1, recommended=True), _candidate(2)]
    runner = SixVLatestRunner(
        repo=repo,
        paths=paths,
        target_count=2,
        batch_size=1,
        snapshot_max_requests=2,
        batch_max_requests=2,
        crawler_builder=lambda _policy: _FakeCrawler(candidates, calls),
    )
    first = runner.run(refresh=True, max_batches=1)
    assert first.status == "pending"
    assert first.covered_count == 1
    status = read_latest_status(
        repo=repo,
        paths=paths,
        source_id="sixv",
        target_count=2,
    )
    assert status["status"] == "pending"
    assert [item["rank"] for item in status["unresolved"]] == [2]
    second = runner.run(refresh=False)
    assert second.status == "success"
    assert second.covered_count == 2
    before = dict(calls)
    third = runner.run(refresh=False)
    assert third.status == "success"
    assert calls == before
    feed = json.loads(paths.feed_path.read_text(encoding="utf-8"))
    assert [item["rank"] for item in feed["items"]] == [1, 2]
    assert feed["items"][0]["recommended"] is True
    assert feed["items"][0]["highlight_labels"] == ["推荐"]
    repo.close()


class _IncompleteCrawler(_FakeCrawler):
    def crawl_movie_detail(self, candidate: SixVListingCandidate):
        self.calls["detail"] += 1
        self.http_requests += 1
        return replace(
            _detail(candidate),
            genres=(),
            directors=(),
            actors=(),
            synopsis=None,
        )


class _InterruptingCrawler(_FakeCrawler):
    def crawl_movie_detail(self, candidate: SixVListingCandidate):
        self.calls["detail"] += 1
        self.http_requests += 1
        if candidate.rank == 2:
            raise KeyboardInterrupt
        return _detail(candidate)


class _RateLimitedCrawler(_FakeCrawler):
    def crawl_movie_detail(self, candidate: SixVListingCandidate):
        self.calls["detail"] += 1
        self.http_requests += 1
        if candidate.rank == 2:
            raise ResourceIndexError(
                LIVE_RATE_LIMITED,
                "temporary source rate limit",
                {"rank": candidate.rank},
            )
        return _detail(candidate)


def test_movie_repository_does_not_regress_nonempty_structured_fields(tmp_path: Path) -> None:
    repo = SqliteResourceRepository(tmp_path / "movie.db")
    repo.init_schema()
    store = MovieRepository(repo)
    complete = _detail(_candidate(1))
    store.upsert(complete, now=NOW)
    store.upsert(
        replace(
            complete,
            countries=(),
            genres=(),
            languages=(),
            directors=(),
            actors=(),
            quality_tags=(),
            synopsis=None,
        ),
        now=NOW,
    )
    item = store.feed_item(
        source_id="sixv",
        detail_url=complete.detail_url,
        rank=1,
    )
    assert item is not None
    assert item["countries"] == ["中国大陆"]
    assert item["genres"] == ["动作"]
    assert item["languages"] == ["汉语普通话"]
    assert item["directors"] == ["导演"]
    assert item["actors"] == ["演员"]
    assert item["quality_tags"] == ["1080p", "HD", "中字"]
    assert item["synopsis"] == "简介"
    repo.close()


def test_sixv_runner_reparses_only_incomplete_items(tmp_path: Path) -> None:
    paths = LatestCrawlPaths.for_output_dir(
        tmp_path / "out",
        source_id="sixv",
        target_count=1,
    )
    repo = SqliteResourceRepository(paths.db_path)
    candidates = [_candidate(1)]
    initial_calls = {"snapshot": 0, "detail": 0}
    initial = SixVLatestRunner(
        repo=repo,
        paths=paths,
        target_count=1,
        batch_size=1,
        snapshot_max_requests=2,
        batch_max_requests=2,
        crawler_builder=lambda _policy: _IncompleteCrawler(candidates, initial_calls),
    )
    first = initial.run(refresh=True)
    assert first.status == "success"
    assert initial_calls == {"snapshot": 1, "detail": 1}

    repair_calls = {"snapshot": 0, "detail": 0}
    repaired = SixVLatestRunner(
        repo=repo,
        paths=paths,
        target_count=1,
        batch_size=1,
        snapshot_max_requests=2,
        batch_max_requests=2,
        crawler_builder=lambda _policy: _FakeCrawler(candidates, repair_calls),
    )
    second = repaired.run(refresh=False, reparse_incomplete=True)
    assert second.status == "success"
    assert repair_calls == {"snapshot": 0, "detail": 1}
    item = repaired.movie_repo.feed_item(
        source_id="sixv",
        detail_url=candidates[0].detail_url,
        rank=1,
    )
    assert item is not None
    assert item["genres"] == ["动作"]
    assert item["synopsis"] == "简介"

    before = dict(repair_calls)
    third = repaired.run(refresh=False)
    assert third.status == "success"
    assert repair_calls == before
    repo.close()


def test_sixv_runner_cancel_resets_unvisited_items_and_resumes(tmp_path: Path) -> None:
    paths = LatestCrawlPaths.for_output_dir(
        tmp_path / "out",
        source_id="sixv",
        target_count=3,
    )
    repo = SqliteResourceRepository(paths.db_path)
    candidates = [_candidate(1), _candidate(2), _candidate(3)]
    calls = {"snapshot": 0, "detail": 0}
    interrupted = SixVLatestRunner(
        repo=repo,
        paths=paths,
        target_count=3,
        batch_size=3,
        snapshot_max_requests=2,
        batch_max_requests=4,
        crawler_builder=lambda _policy: _InterruptingCrawler(candidates, calls),
    )
    with pytest.raises(KeyboardInterrupt):
        interrupted.run(refresh=True)

    items = interrupted.job_store.items(interrupted.current_job_id)
    assert [(item["rank"], item["status"], item["attempts"]) for item in items] == [
        (1, "success", 1),
        (2, "failed", 1),
        (3, "pending", 0),
    ]
    assert calls["detail"] == 2

    resumed_calls = {"snapshot": 0, "detail": 0}
    resumed = SixVLatestRunner(
        repo=repo,
        paths=paths,
        target_count=3,
        batch_size=3,
        snapshot_max_requests=2,
        batch_max_requests=4,
        crawler_builder=lambda _policy: _FakeCrawler(candidates, resumed_calls),
    )
    result = resumed.run(refresh=False)
    assert result.status == "success"
    assert resumed_calls == {"snapshot": 0, "detail": 2}
    repo.close()


def test_sixv_runner_rate_limit_pauses_without_touching_later_items(tmp_path: Path) -> None:
    paths = LatestCrawlPaths.for_output_dir(
        tmp_path / "out",
        source_id="sixv",
        target_count=3,
    )
    repo = SqliteResourceRepository(paths.db_path)
    candidates = [_candidate(1), _candidate(2), _candidate(3)]
    calls = {"snapshot": 0, "detail": 0}
    runner = SixVLatestRunner(
        repo=repo,
        paths=paths,
        target_count=3,
        batch_size=3,
        snapshot_max_requests=2,
        batch_max_requests=4,
        crawler_builder=lambda _policy: _RateLimitedCrawler(candidates, calls),
    )
    result = runner.run(refresh=True)
    assert result.status == "paused"
    assert calls == {"snapshot": 1, "detail": 2}
    items = runner.job_store.items(runner.current_job_id)
    assert [(item["rank"], item["status"], item["attempts"]) for item in items] == [
        (1, "success", 1),
        (2, "failed", 1),
        (3, "pending", 0),
    ]
    repo.close()
