"""Meijumi latest-series adapter contracts."""

from __future__ import annotations

from datetime import date

from magnet.resource_index.adapters.meijumi.parser import (
    parse_latest_listing,
    parse_series_detail,
)

LISTING_HTML = """
<html><body><ol>
<li class="news100">
<span class="zuo"><a href="https://www.meijumi.net/45412.html">深信之疑第一季</a></span>
<span class="zhong">第1集</span>
<span class="buxianshi"><a>2026新剧</a> | <a>罪案/动作谍战</a></span>
<span class="you">2026-07-25</span>
</li>
<li class="news100">
<span class="zuo"><a href="/45410.html">绝命熊帮第一季</a></span>
<span class="zhong">无字第2集</span>
<span class="buxianshi"><a>动漫/动画</a></span>
<span class="you">2026-07-25</span>
</li>
</ol></body></html>
"""

DETAIL_HTML = """
<html><body><h1>《深信之疑第一季》The Truthers 网盘/迅雷下载</h1>
<div class="single-content">
<div class="shangbu">
<blockquote><p>母亲离世后，露丝回到故乡调查真相。</p></blockquote>
<img src="https://img.example/truthers.jpg">
<p>• 中文译名 : 深信之疑 第一季 / 深信之渊 /
• 外语原名 : The Truthers Season 1 / Los creyentes
• 制作地区 : 西班牙
• 类       别 : 悬疑 / 犯罪 / 惊悚
• 语       言 : 西班牙语
• 首映时间 : 2026-07-24(西班牙)
• 季       数 : 1
• 单集片长 : 105min
• 主       演 : 何塞·科罗纳多 / Noémie Dulau
• 导       演 : 罗热·瓜尔
• 豆瓣评分 : 7.2/10
• 更       新 : 第1集</p>
</div>
<div class="diibu">
<p>S01E01.中英字幕.1080P |
<a href="magnet:?xt=urn:btih:97430cd2a109439fc6e7da6b7ace7c4e6d53127c">磁力</a> |
<a href="https://pan.xunlei.com/s/example?pwd=8zd3">迅雷盘</a> |
<a href="https://pan.quark.cn/s/example">夸克盘</a></p>
</div></div></body></html>
"""


def test_meijumi_listing_extracts_series_update_identity() -> None:
    items = parse_latest_listing(
        LISTING_HTML,
        page_url="https://www.meijumi.net/news/",
    )
    assert len(items) == 2
    assert items[0].content_kind == "series"
    assert items[0].series_title == "深信之疑第一季"
    assert items[0].season_number == 1
    assert items[0].episode_number == 1
    assert items[0].episode_label == "第1集"
    assert items[0].update_date == date(2026, 7, 25)
    assert items[0].source_item_key == "/45412.html"
    assert items[0].brand_id == "meijumi"
    assert items[1].episode_number == 2


def test_meijumi_listing_prefers_current_season_and_completed_episode_count() -> None:
    html = """
    <li class="news100">
      <span class="zuo"><a href="/41232.html">谜探休格第一至二季</a></span>
      <span class="zhong">第二季 第6集</span>
      <span class="buxianshi"><a>罪案/动作谍战</a></span>
      <span class="you">2026-07-25</span>
    </li>
    <li class="news100">
      <span class="zuo"><a href="/45383.html">接招合唱团:英国乐团传奇</a></span>
      <span class="zhong">全3集</span>
      <span class="buxianshi"><a>纪录片</a></span>
      <span class="you">2026-07-24</span>
    </li>
    """
    items = parse_latest_listing(html, page_url="https://www.meijumi.net/news/")
    assert items[0].season_number == 2
    assert items[0].episode_number == 6
    assert items[1].episode_number == 3


def test_meijumi_detail_extracts_metadata_cover_and_public_resources() -> None:
    candidate = parse_latest_listing(
        LISTING_HTML,
        page_url="https://www.meijumi.net/news/",
    )[0]
    detail = parse_series_detail(DETAIL_HTML, candidate=candidate)
    assert detail.content_kind == "series"
    assert detail.title == "深信之疑 第一季"
    assert detail.original_title == "The Truthers Season 1"
    assert detail.year == 2026
    assert detail.release_date == date(2026, 7, 24)
    assert detail.duration_minutes == 105
    assert detail.countries == ("西班牙",)
    assert detail.genres == ("悬疑", "犯罪", "惊悚")
    assert detail.directors == ("罗热·瓜尔",)
    assert detail.actors == ("何塞·科罗纳多", "Noémie Dulau")
    assert detail.cover_source_url == "https://img.example/truthers.jpg"
    assert detail.synopsis == "母亲离世后,露丝回到故乡调查真相。"
    assert {(item.resource_type, item.provider) for item in detail.resources} == {
        ("magnet", "magnet"),
        ("cloud", "xunlei"),
        ("cloud", "quark"),
    }
    xunlei = next(item for item in detail.resources if item.provider == "xunlei")
    assert xunlei.extraction_code == "8zd3"


def test_meijumi_detail_ignores_non_http_ed2k_href_with_bracketed_filename() -> None:
    candidate = parse_latest_listing(
        LISTING_HTML,
        page_url="https://www.meijumi.net/news/",
    )[0]
    html = """
    <html><body><h1>《无神第一季》Godless</h1>
    <div class="single-content"><div class="diibu"><p>
    <a href="ed2k://|file|[V2]Godless.S01E07.720p.mp4|1313708240|B056FF125FF06CE28A178663B367A296|/">ED2K</a>
    <a href="magnet:?xt=urn:btih:287b058e05099cec381b20bce3f8d21b6e90ece9">磁力</a>
    </p></div></div></body></html>
    """

    detail = parse_series_detail(html, candidate=candidate)

    assert len(detail.resources) == 1
    assert detail.resources[0].resource_type == "magnet"
    assert detail.resources[0].info_hash == "287b058e05099cec381b20bce3f8d21b6e90ece9"
