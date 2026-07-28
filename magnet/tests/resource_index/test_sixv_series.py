"""SixV latest-series source contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from magnet.resource_index.acquisition.policy import LiveFetchPolicy
from magnet.resource_index.adapters.sixv.series_crawler import SixVSeriesLiveCrawler
from magnet.resource_index.adapters.sixv.series_parser import (
    parse_latest_series_listing,
    parse_series_detail,
)

LISTING_HTML = """
<html><body><div id="main"><ul class="list">
<li><span>[07-26]</span><a href="/dlz/2026-07-21/50027.html">《江海潮生》更新09</a></li>
<li><span>[07-26]</span><a href="/rj/2026-06-27/49886.html">韩剧《金特务：本色回归》全集</a></li>
<li><span>[07-24]</span><a href="/mj/2026-07-24/50046.html">美剧《斯图尔特未能拯救宇宙》第一季01</a></li>
</ul></div></body></html>
"""

DETAIL_HTML = """
<html><body><h1>美剧《斯图尔特未能拯救宇宙》第一季01</h1>
<div id="endText">
<p><img src="https://img.example/stuart.jpg"></p>
<p>◎标　　题　斯图尔特未能拯救宇宙</p>
<p>◎年　　代　2026</p>
<p>◎产　　地　美国</p>
<p>◎类　　别　剧情/喜剧</p>
<p>◎语　　言　英语</p>
<p>◎简　　介</p><p>一段电视剧简介。</p>
<hr><p><a href="magnet:?xt=urn:btih:97430cd2a109439fc6e7da6b7ace7c4e6d53127c">S01E01.1080p</a></p>
</div></body></html>
"""


def test_sixv_series_listing_extracts_latest_order_and_episode_state() -> None:
    items = parse_latest_series_listing(
        LISTING_HTML,
        page_url="https://www.6v520.com/gvod/dsj.html",
        reference_date=date(2026, 7, 26),
    )
    assert len(items) == 3
    assert [item.rank for item in items] == [1, 2, 3]
    assert items[0].series_title == "江海潮生"
    assert items[0].episode_number == 9
    assert items[0].update_status == "更新09"
    assert items[0].update_date == date(2026, 7, 26)
    assert items[1].episode_number is None
    assert items[1].update_status == "全集"
    assert items[2].season_number == 1
    assert items[2].episode_number == 1
    assert items[2].content_kind == "series"
    assert items[2].brand_id == "sixv"


def test_sixv_series_detail_reuses_sixv_detail_parser() -> None:
    candidate = parse_latest_series_listing(
        LISTING_HTML,
        page_url="https://www.6v520.com/gvod/dsj.html",
        reference_date=date(2026, 7, 26),
    )[2]
    detail = parse_series_detail(DETAIL_HTML, candidate=candidate)
    assert detail.source_id == "sixv-series"
    assert detail.content_kind == "series"
    assert detail.series_title == "斯图尔特未能拯救宇宙"
    assert detail.season_number == 1
    assert detail.episode_number == 1
    assert detail.title == "斯图尔特未能拯救宇宙"
    assert detail.genres == ("剧情", "喜剧")
    assert detail.cover_source_url == "https://img.example/stuart.jpg"
    assert detail.synopsis == "一段电视剧简介。"
    assert len(detail.resources) == 1


@dataclass
class _FakeResponse:
    url: str
    content: bytes


class _FakeSeriesClient:
    def __init__(self, pages: dict[str, str]) -> None:
        self.pages = pages
        self.calls: list[str] = []

    def get(self, url: str, **_kwargs) -> _FakeResponse:
        self.calls.append(url)
        return _FakeResponse(url=url, content=self.pages.get(url, "<html></html>").encode("utf-8"))


def _listing(*rows: tuple[str, str]) -> str:
    items = "".join(
        f'<li><span>[07-26]</span><a href="{path}">{title}</a></li>'
        for path, title in rows
    )
    return f'<html><body><div id="main"><ul class="list">{items}</ul></div></body></html>'


def test_sixv_series_crawler_expands_archives_and_deduplicates() -> None:
    origin = "https://www.6v520.com"
    pages = {
        f"{origin}/gvod/dsj.html": _listing(
            ("/dlz/2026-07-21/50027.html", "《江海潮生》更新09"),
            ("/rj/2026-06-27/49886.html", "韩剧《金特务》全集"),
        ),
        f"{origin}/dlz/": _listing(
            ("/dlz/2026-07-21/50027.html", "《江海潮生》更新09"),
            ("/dlz/2026-07-20/50026.html", "《国产新剧》更新08"),
        ),
        f"{origin}/rj/": _listing(
            ("/rj/2026-07-20/50025.html", "韩剧《日韩新剧》更新07"),
        ),
        f"{origin}/mj/": _listing(
            ("/mj/2026-07-20/50024.html", "美剧《欧美新剧》第一季06"),
        ),
    }
    client = _FakeSeriesClient(pages)
    crawler = SixVSeriesLiveCrawler(
        policy=LiveFetchPolicy(
            enabled=True,
            acknowledged=True,
            max_pages=10,
            request_delay_seconds=10.0,
        ),
        client=client,  # type: ignore[arg-type]
        today=date(2026, 7, 26),
    )

    items = crawler.crawl_latest_candidates(limit=5, max_listing_pages=4)

    assert [item.rank for item in items] == [1, 2, 3, 4, 5]
    assert len({item.detail_url for item in items}) == 5
    assert client.calls == [
        f"{origin}/gvod/dsj.html",
        f"{origin}/dlz/",
        f"{origin}/rj/",
        f"{origin}/mj/",
    ]
