"""Pure parsers for Bitba latest-series pages."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from magnet.resource_index.domain.movie_models import MovieDetail, MovieListingCandidate, MovieResource
from magnet.resource_index.normalize.magnets import normalize_magnet_uri
from magnet.resource_index.normalize.text import normalize_whitespace

SOURCE_ID = "bitba-series"
ORIGIN = "https://www.bitba.net"
PARSER_VERSION = "bitba-series-parser/1.2.0"

_APP_COUNTRY_ALIASES = {
    "中国": "中国",
    "中国大陆": "中国",
    "大陆": "中国",
    "中华人民共和国": "中国",
    "香港": "香港",
    "中国香港": "香港",
    "香港特别行政区": "香港",
    "台湾": "台湾",
    "中国台湾": "台湾",
    "台湾地区": "台湾",
    "美国": "美国",
    "usa": "美国",
    "united states": "美国",
    "英国": "英国",
    "uk": "英国",
    "united kingdom": "英国",
    "日本": "日本",
    "japan": "日本",
    "韩国": "韩国",
    "南韩": "韩国",
    "south korea": "韩国",
    "korea": "韩国",
}

_QUALITY_PATTERNS = (
    (re.compile(r"(?i)(?:2160p|4k)"), "4K"),
    (re.compile(r"(?i)1080p"), "1080p"),
    (re.compile(r"(?i)720p"), "720p"),
    (re.compile(r"(?i)HDR"), "HDR"),
    (re.compile(r"(?i)(?:DV|Dolby Vision|杜比视界)"), "杜比视界"),
    (re.compile(r"(?i)60\s*fps|60帧"), "60fps"),
    (re.compile(r"国语"), "国语"),
    (re.compile(r"粤语"), "粤语"),
    (re.compile(r"中英(?:双)?字(?:幕)?"), "中英双字"),
    (re.compile(r"中字(?:幕)?"), "中字"),
)


def extract_quality_tags(*values: str | None) -> tuple[str, ...]:
    text = " ".join(value for value in values if value)
    output: list[str] = []
    for pattern, label in _QUALITY_PATTERNS:
        if pattern.search(text) and label not in output:
            output.append(label)
    return tuple(output)


def _content_code(detail_url: str) -> str:
    match = re.search(r"/bt/(\d+)\.html$", urlparse(detail_url).path)
    return match.group(1) if match else hashlib.sha256(detail_url.encode("utf-8")).hexdigest()[:16]


def _season_number(value: str) -> int | None:
    values = [int(item) for item in re.findall(r"第\s*(\d{1,2})\s*季", value)]
    values.extend(int(item) for item in re.findall(r"(?i)\bS(\d{1,2})(?:E\d+)?\b", value))
    return max(values) if values else None


def _episode_number(value: str) -> int | None:
    values: list[int] = []
    for pattern in (
        r"第\s*0*(\d{1,4})\s*集",
        r"全\s*0*(\d{1,4})\s*集",
        r"更新至?\s*0*(\d{1,4})",
        r"(?i)\bS\d{1,2}E0*(\d{1,4})\b",
    ):
        values.extend(int(item) for item in re.findall(pattern, value))
    return max(values) if values else None


def _app_countries(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    normalized = normalize_whitespace(value)
    output: list[str] = []
    for token in re.split(r"\s*(?:/|、|,|，|\||·)\s*|\s{2,}", normalized):
        cleaned = normalize_whitespace(token)
        if not cleaned:
            continue
        mapped = _APP_COUNTRY_ALIASES.get(cleaned.casefold()) or _APP_COUNTRY_ALIASES.get(cleaned)
        if mapped and mapped not in output:
            output.append(mapped)
    if not output:
        mapped = _APP_COUNTRY_ALIASES.get(normalized.casefold()) or _APP_COUNTRY_ALIASES.get(normalized)
        if mapped:
            output.append(mapped)
    return tuple(output)


def _country_text(container: BeautifulSoup) -> str | None:
    for row in container.select(".item-info-row, .pcard-info p"):
        label = row.find(["b", "strong"])
        if label is None or normalize_whitespace(label.get_text(" ", strip=True)) != "地区":
            continue
        text = normalize_whitespace(row.get_text(" ", strip=True))
        value = normalize_whitespace(text.removeprefix("地区"))
        if value:
            return value
    return None


def parse_latest_listing(
    html: str,
    *,
    page_url: str,
    rank_offset: int = 0,
) -> list[MovieListingCandidate]:
    soup = BeautifulSoup(html, "html.parser")
    page_origin = f"{urlparse(page_url).scheme}://{urlparse(page_url).netloc}"
    output: list[MovieListingCandidate] = []
    for card in soup.select("ul.pgrid li.pcard"):
        anchor = card.select_one("a.pcard-link[href]")
        if anchor is None:
            continue
        detail_url = urljoin(page_url, str(anchor.get("href") or ""))
        if not re.fullmatch(r"/bt/\d+\.html", urlparse(detail_url).path):
            continue
        title = normalize_whitespace(
            str(anchor.get("title") or "")
            or (
                card.select_one(".pcard-title").get_text(" ", strip=True)
                if card.select_one(".pcard-title") is not None
                else ""
            )
        )
        if not title:
            continue
        if not _app_countries(_country_text(card)):
            continue
        badge = card.select_one(".pcard-badge")
        update_status = normalize_whitespace(badge.get_text(" ", strip=True)) if badge is not None else None
        year_node = card.select_one(".pcard-year")
        year_text = normalize_whitespace(year_node.get_text(" ", strip=True)) if year_node is not None else ""
        listing_title = normalize_whitespace(" ".join(value for value in (title, year_text, update_status) if value))
        output.append(
            MovieListingCandidate(
                rank=rank_offset + len(output) + 1,
                detail_url=detail_url,
                source_item_key=urlparse(detail_url).path,
                content_code=_content_code(detail_url),
                listing_title=listing_title,
                update_date=None,
                recommended=False,
                highlight_labels=(),
                quality_tags=extract_quality_tags(listing_title),
                content_kind="series",
                series_title=normalize_whitespace(title.split("/")[0]),
                season_number=_season_number(title),
                episode_number=_episode_number(update_status or title),
                episode_label=update_status or None,
                update_status=update_status or None,
                brand_id="bitba",
                endpoint_origin=page_origin,
            )
        )
    return output


def _json_ld_graph(soup: BeautifulSoup) -> list[dict]:
    output: list[dict] = []
    for node in soup.select('script[type="application/ld+json"]'):
        try:
            payload = json.loads(node.get_text())
        except (json.JSONDecodeError, TypeError):
            continue
        values = payload.get("@graph") if isinstance(payload, dict) else None
        if isinstance(values, list):
            output.extend(item for item in values if isinstance(item, dict))
        elif isinstance(payload, dict):
            output.append(payload)
    return output


def _entity(graph: list[dict]) -> dict:
    for item in graph:
        kind = item.get("@type")
        kinds = kind if isinstance(kind, list) else [kind]
        if any(value in {"TVSeries", "TVSeason", "Movie"} for value in kinds):
            return item
    return {}


def _webpage(graph: list[dict]) -> dict:
    for item in graph:
        kind = item.get("@type")
        kinds = kind if isinstance(kind, list) else [kind]
        if "WebPage" in kinds:
            return item
    return {}


def _person_names(value: object) -> tuple[str, ...]:
    items = value if isinstance(value, list) else [value]
    output: list[str] = []
    for item in items:
        name = item.get("name") if isinstance(item, dict) else item
        cleaned = normalize_whitespace(str(name or ""))
        if cleaned and cleaned not in output:
            output.append(cleaned)
    return tuple(output)


def _string_values(value: object) -> tuple[str, ...]:
    items = value if isinstance(value, list) else [value]
    output: list[str] = []
    for item in items:
        cleaned = normalize_whitespace(str(item or ""))
        if cleaned and cleaned not in output:
            output.append(cleaned)
    return tuple(output)


def _date(value: object) -> date | None:
    text = str(value or "")
    match = re.search(r"(19\d{2}|20\d{2})-(\d{2})-(\d{2})", text)
    if not match:
        return None
    try:
        return date.fromisoformat(match.group(0))
    except ValueError:
        return None


def _image_url(value: object) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, list) and value:
        return _image_url(value[0])
    if isinstance(value, dict):
        for key in ("url", "contentUrl"):
            if isinstance(value.get(key), str):
                return str(value[key])
    return None


def _resources(entity: dict) -> tuple[MovieResource, ...]:
    raw_offers = entity.get("offers")
    offers = raw_offers if isinstance(raw_offers, list) else [raw_offers]
    output: list[MovieResource] = []
    seen: set[str] = set()
    for offer in offers:
        if not isinstance(offer, dict):
            continue
        url = str(offer.get("url") or "")
        match = re.search(r"/down/\d+/([a-fA-F0-9]{40})\.html(?:$|[?#])", url)
        if not match:
            continue
        info_hash = match.group(1).lower()
        if info_hash in seen:
            continue
        name = normalize_whitespace(str(offer.get("name") or info_hash))
        try:
            magnet, normalized_hash = normalize_magnet_uri(
                f"magnet:?xt=urn:btih:{info_hash}",
                fallback_dn=name,
            )
        except Exception:
            continue
        seen.add(normalized_hash)
        output.append(
            MovieResource(
                resource_type="magnet",
                provider="magnet",
                resource_url=magnet,
                info_hash=normalized_hash,
                display_title=name,
                extraction_code=None,
                quality_tags=extract_quality_tags(name),
            )
        )
    return tuple(output)


def parse_series_detail(
    html: str,
    *,
    candidate: MovieListingCandidate,
    raw_content: bytes | None = None,
) -> MovieDetail:
    soup = BeautifulSoup(html, "html.parser")
    graph = _json_ld_graph(soup)
    entity = _entity(graph)
    webpage = _webpage(graph)
    title = normalize_whitespace(str(entity.get("name") or candidate.series_title or candidate.listing_title))
    alternate = entity.get("alternateName")
    alternates = _string_values(alternate)
    original_title = alternates[0] if alternates else None
    release_date = _date(entity.get("datePublished"))
    year_match = re.search(r"(19\d{2}|20\d{2})", candidate.listing_title)
    year = release_date.year if release_date is not None else (int(year_match.group(1)) if year_match else None)
    genres = tuple(value for value in _string_values(entity.get("genre")) if value not in {"剧集", "电视剧"})
    resources = _resources(entity)
    countries = _app_countries(_country_text(soup))
    if not countries:
        raise ValueError("Bitba detail page is missing an App-compatible country")
    quality_tags = list(candidate.quality_tags)
    for resource in resources:
        for label in resource.quality_tags:
            if label not in quality_tags:
                quality_tags.append(label)
    raw_hash = hashlib.sha256(raw_content if raw_content is not None else html.encode("utf-8")).hexdigest()
    return MovieDetail(
        source_id=SOURCE_ID,
        source_item_key=candidate.source_item_key,
        content_code=candidate.content_code,
        detail_url=candidate.detail_url,
        listing_title=candidate.listing_title,
        title=title,
        original_title=original_title,
        year=year,
        update_date=_date(webpage.get("dateModified")) or candidate.update_date,
        release_date=release_date,
        duration_minutes=None,
        countries=countries,
        genres=genres,
        languages=(),
        directors=_person_names(entity.get("director")),
        actors=_person_names(entity.get("actor")),
        imdb_id=None,
        douban_rating=None,
        douban_rating_text=None,
        douban_url=None,
        cover_source_url=_image_url(entity.get("image")),
        synopsis=normalize_whitespace(str(entity.get("description") or "")) or None,
        recommended=False,
        highlight_labels=(),
        quality_tags=tuple(quality_tags),
        parser_version=PARSER_VERSION,
        raw_document_hash=raw_hash,
        resources=resources,
        content_kind="series",
        series_title=candidate.series_title or title,
        season_number=candidate.season_number or _season_number(title + " " + (original_title or "")),
        episode_number=candidate.episode_number,
        episode_label=candidate.episode_label,
        update_status=candidate.update_status,
        brand_id="bitba",
        endpoint_origin=candidate.endpoint_origin or ORIGIN,
    )
