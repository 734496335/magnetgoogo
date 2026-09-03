from __future__ import annotations

from datetime import date

from magnet.resource_index.adapters.bitba.parser import (
    parse_latest_listing as parse_bitba_listing,
    parse_series_detail as parse_bitba_detail,
)
from magnet.resource_index.adapters.dytt.series_parser import (
    parse_latest_listing as parse_dytt_series_listing,
    parse_series_detail as parse_dytt_series_detail,
)
from magnet.resource_index.adapters.mjf.parser import (
    latest_resource_page_url,
    parse_latest_listing as parse_mjf_listing,
    parse_series_detail as parse_mjf_detail,
)
from magnet.resource_index.adapters.movie_registry import list_movie_sources


BITBA_LISTING = """
<ul class="pgrid">
  <li class="pcard">
    <a class="pcard-link" href="https://www.bitba.net/bt/2710177811.html" title="师兄太稳健">
      <span class="pcard-year">2026</span>
      <span class="pcard-badge">第25集</span>
      <div class="pcard-title">师兄太稳健</div>
      <div class="pcard-info"><p><b>地区</b>中国大陆</p></div>
    </a>
  </li>
</ul>
"""

BITBA_DETAIL = """
<html><head>
<script type="application/ld+json">
{
  "@context": "http://schema.org",
  "@graph": [
    {
      "@type": "WebPage",
      "dateModified": "2026-09-02T13:13:13+08:00"
    },
    {
      "@type": "TVSeries",
      "name": "师兄太稳健",
      "alternateName": ["我师兄实在太稳健了"],
      "image": "https://img.example/cover.jpg",
      "actor": [{"@type":"Person","name":"演员甲"}],
      "director": [{"@type":"Person","name":"导演甲"}],
      "genre": ["剧集", "剧情", "奇幻"],
      "description": "剧集简介",
      "datePublished": "2026-08-19",
      "offers": [
        {"@type":"Offer","name":"师兄太稳健.S01E25.2160p.HDR","url":"https://www.bitba.net/down/2710177811/5890fd8776c03dafda00bf6ca9a04cb8b185db6d.html"},
        {"@type":"Offer","name":"duplicate","url":"https://www.bitba.net/down/2710177811/5890fd8776c03dafda00bf6ca9a04cb8b185db6d.html"},
        {"@type":"Offer","name":"师兄太稳健.S01E25.1080p","url":"https://www.bitba.net/down/2710177811/2931c82a9e69a3e44538095fd62e603af20f58c6.html"}
      ]
    }
  ]
}
</script>
</head><body><h1>师兄太稳健</h1><div class="item-info-row"><b>地区</b>中国大陆</div></body></html>
"""

DYTT_LISTING = """
<table class="tbspan"><tr><td>
<a class="ulink" href="/i/123229.html" title="2026年日本电视剧《出轨禁止》 连载至第01集">2026年日本电视剧《出轨禁止》 连载至第01集</a>
</td></tr></table>
"""

DYTT_DETAIL = """
<html><body><h1>2026年日本电视剧《出轨禁止》</h1>
<div id="Zoom">
<p>◎片名　出轨禁止</p>
<p>◎年代　2026</p>
<p>◎产地　日本</p>
<p>◎类别　剧情/爱情</p>
<p>◎导演　导演乙</p>
<p>◎主演　演员乙</p>
<p>◎简介　测试简介</p>
<img src="/covers/123229.jpg" />
<a href="magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef01234567">出轨禁止.S01E01.1080p</a>
</div></body></html>
"""

MJF_LISTING = """
<ul>
<li class="list-group-item text-nowrap-ellipsis">
<a href="/jianjie/42547.html" title="行尸走肉：死亡之城(The Walking Dead: Dead City)">行尸走肉：死亡之城(The Walking Dead: Dead City)</a>
<a>更新时间：<span>1天前</span></a>
</li>
</ul>
"""

MJF_DETAIL = """
<html><head>
<meta property="og:image" content="https://img.example/dead-city.jpg" />
<meta name="description" content="行尸走肉：死亡之城简介" />
</head><body>
<h1>行尸走肉：死亡之城</h1>
<div>IMDB: tt18546730</div>
<div>别名: 死亡之岛</div>
<div>英文名字: The Walking Dead: Dead City</div>
<div>电视台: AMC</div>
<div>类型: 剧情/恐怖/惊悚</div>
<div>状态: 第3季连载</div>
<div>首播: 2023-06-18 周日</div>
<a href="/bt/42547219016.html">第3季- 第6集</a>
</body></html>
"""

MJF_RESOURCE = """
<html><body><h1>The Walking Dead Dead City S03E06 1080p WEB h264-ETHEL</h1>
<textarea id="link-input" readonly>magnet:?xt=urn:btih:DF4E9CEE9C83AA2F1FFC065DD5F4751D858DD918&amp;dn=Dead+City+S03E06</textarea>
</body></html>
"""


def test_bitba_series_listing_and_detail_construct_exact_magnets_from_offer_hashes() -> None:
    items = parse_bitba_listing(BITBA_LISTING, page_url="https://www.bitba.net/filter-2.html")
    assert len(items) == 1
    candidate = items[0]
    assert candidate.content_kind == "series"
    assert candidate.series_title == "师兄太稳健"
    assert candidate.episode_number == 25
    assert candidate.brand_id == "bitba"

    detail = parse_bitba_detail(BITBA_DETAIL, candidate=candidate)
    assert detail.source_id == "bitba-series"
    assert detail.title == "师兄太稳健"
    assert detail.original_title == "我师兄实在太稳健了"
    assert detail.year == 2026
    assert detail.update_date is not None
    assert detail.update_date.isoformat() == "2026-09-02"
    assert detail.cover_source_url == "https://img.example/cover.jpg"
    assert detail.countries == ("中国",)
    assert detail.directors == ("导演甲",)
    assert detail.actors == ("演员甲",)
    assert detail.douban_rating is None
    assert len(detail.resources) == 2
    assert [item.info_hash for item in detail.resources] == [
        "5890fd8776c03dafda00bf6ca9a04cb8b185db6d",
        "2931c82a9e69a3e44538095fd62e603af20f58c6",
    ]
    assert all(item.resource_url.startswith("magnet:?xt=urn:btih:") for item in detail.resources)


def test_dytt_series_wrapper_preserves_magnets_and_changes_identity_to_series() -> None:
    items = parse_dytt_series_listing(DYTT_LISTING, page_url="https://www.dytt8899.com/html/tv/rihantv/")
    assert len(items) == 1
    candidate = items[0]
    assert candidate.content_kind == "series"
    assert candidate.series_title == "出轨禁止"
    assert candidate.episode_number == 1
    assert candidate.brand_id == "dytt8899"

    detail = parse_dytt_series_detail(DYTT_DETAIL, candidate=candidate)
    assert detail.source_id == "dytt8899-series"
    assert detail.content_kind == "series"
    assert detail.series_title == "出轨禁止"
    assert detail.year == 2026
    assert len(detail.resources) == 1
    assert detail.resources[0].info_hash == "0123456789abcdef0123456789abcdef01234567"


def test_mjf_series_listing_detail_and_latest_resource_are_bounded_and_fresh() -> None:
    items = parse_mjf_listing(
        MJF_LISTING,
        page_url="https://www.mjf2020.com/gx.html",
        reference_date=date(2026, 9, 2),
    )
    assert len(items) == 1
    candidate = items[0]
    assert candidate.series_title == "行尸走肉:死亡之城"
    assert candidate.update_date == date(2026, 9, 1)
    assert candidate.brand_id == "mjf"
    assert latest_resource_page_url(
        MJF_DETAIL,
        page_url="https://www.mjf2020.com/jianjie/42547.html",
    ) == "https://www.mjf2020.com/bt/42547219016.html"

    detail = parse_mjf_detail(
        MJF_DETAIL,
        candidate=candidate,
        resource_html=MJF_RESOURCE,
    )
    assert detail.source_id == "mjf-series"
    assert detail.title == "行尸走肉:死亡之城"
    assert detail.original_title == "The Walking Dead: Dead City"
    assert detail.imdb_id == "tt18546730"
    assert detail.release_date == date(2023, 6, 18)
    assert detail.season_number == 3
    assert detail.episode_number == 6
    assert detail.cover_source_url == "https://img.example/dead-city.jpg"
    assert detail.countries == ("美国",)
    assert len(detail.resources) == 1
    assert detail.resources[0].info_hash == "df4e9cee9c83aa2f1ffc065dd5f4751d858dd918"
    assert detail.resources[0].resource_type == "magnet"


def test_bitba_listing_excludes_countries_that_existing_app_has_no_series_channel() -> None:
    unsupported = BITBA_LISTING.replace("中国大陆", "墨西哥")
    assert parse_bitba_listing(unsupported, page_url="https://www.bitba.net/filter-2.html") == []


def test_mjf_known_uk_network_maps_to_existing_app_uk_channel() -> None:
    candidate = parse_mjf_listing(
        MJF_LISTING,
        page_url="https://www.mjf2020.com/gx.html",
        reference_date=date(2026, 9, 2),
    )[0]
    detail = parse_mjf_detail(
        MJF_DETAIL.replace("电视台: AMC", "电视台: BBC ONE"),
        candidate=candidate,
        resource_html=MJF_RESOURCE,
    )
    assert detail.countries == ("英国",)


def test_new_series_backup_country_values_are_compatible_with_existing_app_channels() -> None:
    compatible = {"美国", "英国", "韩国", "日本", "中国", "大陆", "香港", "台湾"}
    bitba = parse_bitba_detail(
        BITBA_DETAIL,
        candidate=parse_bitba_listing(BITBA_LISTING, page_url="https://www.bitba.net/filter-2.html")[0],
    )
    mjf = parse_mjf_detail(
        MJF_DETAIL,
        candidate=parse_mjf_listing(
            MJF_LISTING,
            page_url="https://www.mjf2020.com/gx.html",
            reference_date=date(2026, 9, 2),
        )[0],
        resource_html=MJF_RESOURCE,
    )
    assert bitba.countries and set(bitba.countries) <= compatible
    assert mjf.countries and set(mjf.countries) <= compatible


def test_series_backup_sources_are_registered_with_bounded_detail_request_cost() -> None:
    sources = list_movie_sources()
    expected = {
        "dytt8899-series": 1,
        "bitba-series": 1,
        "mjf-series": 2,
    }
    for source_id, request_cost in expected.items():
        assert source_id in sources
        assert sources[source_id]["content_kind"] == "series"
        assert sources[source_id]["catalog_role"] == "supplemental"
        assert sources[source_id]["detail_requests_per_item_upper_bound"] == request_cost
